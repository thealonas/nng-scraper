import os

from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from services.scraper_service import ScraperService


class StoriesRepliesService(ScraperService):
    postgres: NngPostgres
    op: OpConnect

    def __init__(self, postgres: NngPostgres, op: OpConnect):
        super().__init__("stories_replies")
        self.postgres = postgres
        self.op = op

    def run_stories_replies_instance(self, groups: list[str]):
        command = [
            "browserstack-sdk",
            "scripts/stories_replies.py",
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

    def run_stories_replies(self):
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
            "BROWSERSTACK_BUILD_NAME": "stories_replies",
        }

        for key, value in env_vars.items():
            os.environ[key] = value

        groups_in_chunk = 20
        groups_chunks = [
            groups_list[i : i + groups_in_chunk]
            for i in range(0, len(groups_list), groups_in_chunk)
        ]

        self.logger.info("запускаю stories_replies")
        self.logger.info(f"всего сессий: {len(groups_chunks)}")

        for groups_chunk in groups_chunks:
            self.run_stories_replies_instance(groups_chunk)
