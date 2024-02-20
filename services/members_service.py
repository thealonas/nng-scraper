import datetime
import json
import os

from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import Violation, ViolationType, BanPriority

from services.scraper_service import ScraperService


class MembersService(ScraperService):
    postgres: NngPostgres
    op: OpConnect

    def __init__(self, postgres: NngPostgres, op: OpConnect):
        super().__init__("members")
        self.postgres = postgres
        self.op = op

    def get_members_execution_result(self, session_id: str) -> dict[int, list[int]]:
        with open(self.get_session_path(session_id), "r", encoding="utf-8") as f:
            return json.load(f)

    def ban_user(self, user_id: int, group_id: int):
        self.postgres.users.add_violation(
            user_id,
            Violation(
                type=ViolationType.banned,
                group_id=group_id,
                priority=BanPriority.red,
                active=True,
                date=datetime.date.today(),
            ),
        )

    def run_members_instance(self, groups: list[str]):
        command = [
            "browserstack-sdk",
            "scripts/members.py",
            "--browserstack.config",
            "browserstack.yml",
        ]

        session_name = self.generate_session_name()
        self.logger.info(f"запускаю сессию {session_name}")

        stringified_groups = ",".join(groups)
        env_vars = {
            "GROUPS": stringified_groups,
            "SESSION_NAME": session_name,
        }

        for key, value in env_vars.items():
            os.environ[key] = value

        os.system(" ".join(command))

        result = self.get_members_execution_result(session_name).items()

        for index, (group, intruders) in enumerate(result):
            self.logger.info(
                f"обрабатываю группу {group} ({index}/{len(result)}), нарушители: {intruders}"
            )

            for intruder_index, intruder in enumerate(intruders):
                self.logger.info(
                    f"выписываю нарушение {intruder} ({intruder_index + 1}/{len(intruders)})"
                )

                self.ban_user(intruder, group)

    def run_members(self):
        user = self.op.get_scraper_user()
        self.logger.info("получил сервисную страницу для скрапа")

        groups_list = [str(i.group_id) for i in self.postgres.groups.get_all_groups()]

        self.logger.info(f"всего групп: {len(groups_list)}")
        session_name = self.generate_session_name()
        self.logger.info(f"айди сессии: {session_name}")

        browserstack_credentials = self.op.get_browserstack_credentials()

        env_vars = {
            "VK_OTP": user.totp,
            "VK_USERNAME": user.phone,
            "VK_PASSWORD": user.password,
            "BROWSERSTACK_USERNAME": browserstack_credentials.login,
            "BROWSERSTACK_ACCESS_KEY": browserstack_credentials.api_key,
            "BROWSERSTACK_BUILD_NAME": "members",
        }

        for key, value in env_vars.items():
            os.environ[key] = value

        self.logger.info("запускаю members")

        groups_in_chunk = 10
        groups_chunks = [
            groups_list[i : i + groups_in_chunk]
            for i in range(0, len(groups_list), groups_in_chunk)
        ]

        self.logger.info(f"всего сессий: {len(groups_chunks)}")

        for groups_chunk in groups_chunks:
            self.run_members_instance(groups_chunk)
