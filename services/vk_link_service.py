import json
import os

from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres

from helpers.vk_link_helper import VkLinkHelper
from services.scraper_service import ScraperService


class VkLinkService(ScraperService):
    postgres: NngPostgres
    op: OpConnect

    def __init__(self, postgres: NngPostgres, op: OpConnect):
        super().__init__("vk_link")
        self.postgres = postgres
        self.op = op

    def get_execution_result(self, session_id: str) -> dict[int, bool]:
        with open(self.get_session_path(session_id), "r") as f:
            parsed_object: dict[int, bool] = json.load(f)
        return parsed_object

    def run_vk_link(self):
        groups = VkLinkHelper().get_groups_with_sites(
            [i.group_id for i in self.postgres.groups.get_all_groups()]
        )

        self.logger.info(f"всего групп: {len(groups)}")
        if not groups:
            self.logger.info("дальше не продолжаем")
            return

        browserstack_credentials = self.op.get_browserstack_credentials()

        session_name = self.generate_session_name()
        self.logger.info(f"айди сессии: {session_name}")
        user = self.op.get_scraper_user()

        env_vars = {
            "VK_OTP": user.totp,
            "VK_USERNAME": user.phone,
            "VK_PASSWORD": user.password,
            "GROUPS_WITH_LINKS": ",".join(map(str, groups)),
            "SESSION_NAME": session_name,
            "BROWSERSTACK_USERNAME": browserstack_credentials.login,
            "BROWSERSTACK_ACCESS_KEY": browserstack_credentials.api_key,
            "BROWSERSTACK_BUILD_NAME": "vk_link",
        }

        command = [
            "browserstack-sdk",
            "scripts/vk_link.py",
            "--browserstack.config",
            "browserstack.yml",
        ]

        self.logger.info("запускаю vk_link")

        for key, value in env_vars.items():
            os.environ[key] = value

        os.system(" ".join(command))

        results = self.get_execution_result(session_name)
        for group_id, result in results.items():
            if result:
                self.logger.info(f"у группы {group_id} был удален сайт")
            else:
                self.logger.warning(f"не удалось удалить сайт у группы {group_id}")
