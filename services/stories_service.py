import datetime
import json
import os

from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.user import Violation, ViolationType, BanPriority
from vk_api.vk_api import VkApiMethod

from services.scraper_service import ScraperService


class StoriesService(ScraperService):
    postgres: NngPostgres
    op: OpConnect
    vk: VkApiMethod

    def __init__(self, postgres: NngPostgres, op: OpConnect, vk: VkApiMethod):
        super().__init__("stories")
        self.postgres = postgres
        self.op = op
        self.vk = vk

    @staticmethod
    def reformat_link(link: str) -> str:
        if link.startswith("https://vk.com/"):
            return link.replace("https://vk.com/", "")
        elif link.startswith("vk.com/"):
            return link.replace("vk.com/", "")
        else:
            return link

    def get_stories_execution_result(self, session_id: str) -> dict[int, list[str]]:
        with open(self.get_session_path(session_id), "r", encoding="utf-8") as f:
            return json.load(f)

    def resolve_users(self, data: dict[int, list[str]]) -> dict[int, list[int]]:
        if not data.keys():
            return {}

        output: dict[int, list[int]] = {}

        all_users = [user for users in data.values() for user in users]
        all_users = list(set(all_users))
        all_users = [self.reformat_link(i) for i in all_users]

        vk_result = self.vk.users.get(user_ids=all_users, fields="screen_name")

        for group_id, users in data.items():  # проходимся по группам
            output[group_id] = []  # создаем пустой список для группы
            for user in users:  # проходимся по пользователям
                user = self.reformat_link(user)  # форматируем ссылку
                for vk_user in vk_result:  # проходимся по ответу вконтакте
                    if vk_user["screen_name"] == user:  # если нашли пользователя
                        output[group_id].append(vk_user["id"])  # добавляем в список
                        break
                else:
                    self.logger.error(f"не нашел {user} в vk_result")

        return output

    def give_warnings_or_ban(self, user_id: int, group_id: int):
        user = self.postgres.users.get_user(user_id)
        if user.admin:
            self.logger.info(f"не выдаю нарушения {user_id}, ибо он админ")
            return

        new_violation = Violation(
            type=ViolationType.warned,
            group_id=group_id,
            priority=BanPriority.green,
            date=datetime.date.today(),
        )

        active_warnings = [
            i
            for i in user.violations
            if i.type == ViolationType.warned and not i.is_expired()
        ]

        # если меньше двух нарушений
        if user.violations and len(active_warnings) < 3:
            self.logger.info(f"выдал предупреждение {user_id} в {group_id}")
            self.postgres.users.add_violation(user_id, new_violation)
        else:
            self.logger.info(
                f"выдал бан {user_id} в {group_id} ибо у него уже {len(active_warnings)} предупреждений"
            )
            new_violation.type = ViolationType.banned
            new_violation.active = True
            self.postgres.users.add_violation(user_id, new_violation)

    def run_stories_instance(self, groups: list[str]):
        command = [
            "browserstack-sdk",
            "scripts/stories.py",
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

        result = self.get_stories_execution_result(session_name)
        resolved: dict[int, list[int]] = self.resolve_users(result)

        if not resolved:
            self.logger.info("нет нарушителей за сессию")
            return

        for group_id, user_ids in resolved.items():
            for user_id in user_ids:
                self.give_warnings_or_ban(user_id, group_id)

    def run_stories(self):
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
            "BROWSERSTACK_BUILD_NAME": "stories",
        }

        for key, value in env_vars.items():
            os.environ[key] = value

        self.logger.info("запускаю stories")

        groups_in_chunk = 20
        groups_chunks = [
            groups_list[i : i + groups_in_chunk]
            for i in range(0, len(groups_list), groups_in_chunk)
        ]

        self.logger.info(f"всего сессий: {len(groups_chunks)}")

        for groups_chunk in groups_chunks:
            self.run_stories_instance(groups_chunk)
