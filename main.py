import asyncio

import sentry_sdk
from nng_sdk.logger import get_logger
from nng_sdk.one_password.op_connect import OpConnect
from nng_sdk.postgres.nng_postgres import NngPostgres
from nng_sdk.vk.vk_manager import VkManager

from integrations.perspective_api import PerspectiveApi
from services.comments_service import CommentsService
from services.cover_service import CoverService
from services.members_service import MembersService
from services.stories_replies_service import StoriesRepliesService
from services.stories_service import StoriesService
from services.verify_service import VerifyService
from services.vk_link_service import VkLinkService

sentry_sdk.init(
    dsn="https://69452162c48207726ac8cfe920fd9975@o555933.ingest.sentry.io/4506419385270272",
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
)

postgres = NngPostgres()
op = OpConnect()
perspective = PerspectiveApi(op.get_perspective_api())
logger = get_logger()
vk = VkManager()

vk.auth_in_vk()

comments_service = CommentsService(postgres, op, perspective)
verify_service = VerifyService(postgres, op)
vk_link_service = VkLinkService(postgres, op)
cover_service = CoverService(postgres, op)
stories_replies_service = StoriesRepliesService(postgres, op)
stories_service = StoriesService(postgres, op, vk.api)
members_service = MembersService(postgres, op)


def main():
    while True:
        vk_link_service.run_vk_link()
        verify_service.run_verify()
        comments_service.run_comments()
        cover_service.run_covers()
        stories_replies_service.run_stories_replies()
        stories_service.run_stories()
        members_service.run_members()

        logger.info("ожидаю 24 часа")
        asyncio.run(asyncio.sleep(24 * 60 * 60))


if __name__ == "__main__":
    main()
