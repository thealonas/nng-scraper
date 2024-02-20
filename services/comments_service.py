import json
import os

import sentry_sdk
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.pydantic_models.comment import Comment

from services.scraper_service import ScraperService
from integrations.perspective_api import PerspectiveApi


class CommentsService(ScraperService):
    postgres: NngPostgres
    op: OpConnect
    perspective: PerspectiveApi

    def __init__(
        self, postgres: NngPostgres, op: OpConnect, perspective: PerspectiveApi
    ):
        super().__init__("comments")

        self.perspective = perspective
        self.postgres = postgres
        self.op = op

    def get_comments_execution_result(self, session_id: str) -> list[Comment]:
        with open(self.get_session_path(session_id), "r") as f:
            parsed_object: list[Comment] = json.load(f)
        return [Comment.model_validate(i) for i in parsed_object]

    def update_comments(self, comments: list[Comment]):
        for comment in comments:
            if (
                not comment.comment_vk_id
                or not comment.group_id
                or not comment.author_id
                or self.postgres.comments.already_exists(
                    comment.comment_vk_id,
                    comment.group_id,
                    comment.target_group_id,
                    comment.author_id,
                )
            ):
                self.logger.info(
                    f"комментарий -{comment.group_id}_{comment.comment_vk_id} уже присутсвует в бд"
                )
                continue

            if not comment.text and not comment.attachments:
                self.logger.info(f"комментарий {comment.comment_vk_id} пустой")
                continue

            self.logger.info(
                f"анализирую комментарий {comment.comment_vk_id} через perspective..."
            )

            if comment.text:
                try:
                    toxicity_level = self.perspective.analyze_toxicity(comment.text)
                except Exception as e:
                    self.logger.warning(f"ошибка: {e}")
                    sentry_sdk.capture_exception(e)
                    comment.toxicity = 0
                else:
                    comment.toxicity = toxicity_level
            else:
                comment.toxicity = 0

            self.postgres.comments.upload_comment(comment)

    def run_comment_instance(self, groups: list[str]):
        command = [
            "browserstack-sdk",
            "scripts/comment_stats.py",
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

        try:
            comments = self.get_comments_execution_result(session_name)
            self.update_comments(comments)
            self.logger.info(f"комментарии сессии {session_name} обновлены")
            self.cleanup(session_name)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            self.logger.error(f"ошибка при обновлении комментариев: {e}")

    def run_comments(self):
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
            "BROWSERSTACK_BUILD_NAME": "comments",
        }

        for key, value in env_vars.items():
            os.environ[key] = value

        self.logger.info("запускаю comment_stats")

        groups_in_chunk = 5

        groups_chunks = [
            groups_list[i : i + groups_in_chunk]
            for i in range(0, len(groups_list), groups_in_chunk)
        ]

        self.logger.info(f"всего сессий: {len(groups_chunks)}")

        for groups_chunk in groups_chunks:
            self.run_comment_instance(groups_chunk)
