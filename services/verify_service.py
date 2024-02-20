import json
import os
import threading
import time

import sentry_sdk
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.db_models.users import DbUser, DbTrustInfo
from nng_sdk.postgres.nng_postgres import NngPostgres

from services.scraper_service import ScraperService


class VerifyService(ScraperService):
    postgres: NngPostgres
    op: OpConnect

    def __init__(self, postgres: NngPostgres, op: OpConnect):
        super().__init__("verify")
        self.postgres = postgres
        self.op = op

    def get_execution_result(self, session_id: str) -> dict[int, bool]:
        with open(self.get_session_path(session_id), "r") as f:
            parsed_object: dict[str, bool] = json.load(f)
        return {int(user_id): verified for user_id, verified in parsed_object.items()}

    def get_execution_results(self, sessions: list[str]) -> dict[int, bool]:
        output = {}
        for session in sessions:
            output.update(self.get_execution_result(session))
        return output

    def get_unverified_users(self) -> list[str]:
        with self.postgres.begin_session() as session:
            # noinspection PyTypeChecker
            unverified_users: list[DbUser] = (
                session.query(DbUser)
                .join(DbTrustInfo)
                .filter(DbTrustInfo.verified == False)
                .all()
            )

            ids_list = [str(i.user_id) for i in unverified_users]
            return ids_list

    def update_trusts(self, users: dict[int, bool]):
        items = users.items()
        with self.postgres.begin_session() as session:
            for index, (user_id, verified) in enumerate(items):
                self.logger.info(
                    f"обрабатываю {user_id} ({index + 1}/{len(items)}): {'+' if verified else '-'}"
                )
                user = self.postgres.users.get_user(user_id)
                new_trust = user.trust_info
                new_trust.verified = verified
                self.postgres.users.update_user_trust_info(user_id, new_trust, session)

    def run_verify_thread(
        self,
        command: str,
        ids_chunk: list[str],
        session_name: str,
        env_vars: dict[str, str],
        semaphore: threading.Semaphore,
    ):
        with semaphore:
            self.logger.info(f"айди сессии: {session_name}")

            env_vars["UNVERIFIED_USERS"] = ",".join(ids_chunk)
            env_vars["SESSION_NAME"] = session_name
            for key, value in env_vars.items():
                os.environ[key] = value

            os.system(command)
            self.update_trusts(self.get_execution_result(session_name))
            time.sleep(20)

    def run_verify(self):
        user = self.op.get_scraper_user()
        self.logger.info("получил сервисную страницу для скрапа")

        ids_list = self.get_unverified_users()

        self.logger.info(f"всего пользователей: {len(ids_list)}")

        stringified_users = ",".join(ids_list)

        browserstack_credentials = self.op.get_browserstack_credentials()

        env_vars = {
            "VK_OTP": user.totp,
            "VK_USERNAME": user.phone,
            "VK_PASSWORD": user.password,
            "UNVERIFIED_USERS": stringified_users,
            "BROWSERSTACK_USERNAME": browserstack_credentials.login,
            "BROWSERSTACK_ACCESS_KEY": browserstack_credentials.api_key,
            "BROWSERSTACK_BUILD_NAME": "verify",
        }

        command = [
            "browserstack-sdk",
            "scripts/verify.py",
            "--browserstack.config",
            "browserstack.yml",
        ]

        self.logger.info("запускаю verify")

        chunk_size = 500
        user_chunks = [
            ids_list[i : i + chunk_size] for i in range(0, len(ids_list), chunk_size)
        ]
        threads = []
        session_ids = [self.generate_session_name() for _ in user_chunks]

        semaphore = threading.Semaphore(2)

        for index, chunk in enumerate(user_chunks):
            if index > 0:
                time.sleep(90)
            self.logger.info(f"ставлю в очередь {index + 1}й поток")
            thread = threading.Thread(
                target=self.run_verify_thread,
                args=(
                    " ".join(command),
                    chunk,
                    session_ids[index],
                    env_vars.copy(),
                    semaphore,
                ),
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        try:
            self.logger.info("траст факторы обновлены")
            for session in session_ids:
                self.cleanup(session)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            self.logger.error(f"ошибка при обновлении траст факторов: {e}")
