import requests
from nng_sdk.logger import get_logger


class VkLinkHelper:
    LINK_TEMPLATE = "https://vk.link/club{GROUP}"

    logging = get_logger()

    def get_link(self, group_id: int) -> str:
        return self.LINK_TEMPLATE.format(GROUP=group_id)

    def site_exists(self, group_id: int) -> bool:
        group_link = self.get_link(group_id)
        response = requests.get(group_link)
        return response.status_code == 200

    def get_groups_with_sites(self, groups: list[int]):
        self.logging.info(f"всего {len(groups)} групп")

        group_with_sites: list[int] = []
        for group in groups:
            if not self.site_exists(group):
                self.logging.info(f"у группы {group} сайта не найдено")
                continue

            self.logging.info(f"найден сайт у группы {group}")
            group_with_sites.append(group)

        return group_with_sites
