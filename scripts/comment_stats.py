import datetime
import json
import os
import re
import time
from typing import Optional

import pyotp
from bs4 import BeautifulSoup
from dateutil import parser
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

DRIVER_PATH = os.environ.get("DRIVER_PATH")

TOTP = pyotp.TOTP(os.environ.get("VK_OTP"))
PHONE = os.environ.get("VK_USERNAME")
PASSWORD = os.environ.get("VK_PASSWORD")
GROUPS = [int(i) for i in os.environ.get("GROUPS").split(",")]
SESSION_NAME = os.environ.get("SESSION_NAME")

service = webdriver.ChromeService(executable_path=DRIVER_PATH)
options = webdriver.ChromeOptions()
options.add_argument("--blink-settings=imagesEnabled=false")

browser = webdriver.Chrome(service=service, options=options)

VKID_PHONE_INPUT = (
    By.CSS_SELECTOR,
    "input.vkuiInput__el",
)

VKID_PHONE_SUBMIT = (
    By.CSS_SELECTOR,
    "button.vkuiButton--lvl-primary",
)

VKID_OTP_INPUT = (
    By.NAME,
    "otp",
)

VKID_OTP_SUBMIT = (
    By.CSS_SELECTOR,
    "button.vkc__ConfirmOTP__buttonSubmit",
)

VKID_OTP_SUBMIT_ALT = (
    By.CSS_SELECTOR,
    "button.vkc__BottomAuthenticatorOTP__button",
)

VKID_PASSWORD_INPUT = (
    By.NAME,
    "password",
)

VKID_PASSWORD_SUBMIT = (
    By.CSS_SELECTOR,
    "button.vkuiButton--lvl-primary",
)


def retry_code(driver: WebDriver, totp: TOTP):
    WebDriverWait(driver, 5).until(
        expected_conditions.presence_of_element_located(VKID_OTP_INPUT),
    )

    try:
        WebDriverWait(driver, 2).until(
            expected_conditions.presence_of_element_located(VKID_OTP_SUBMIT),
        )
    except TimeoutException:
        WebDriverWait(driver, 2).until(
            expected_conditions.presence_of_element_located(VKID_OTP_SUBMIT_ALT),
        )

    code = totp.now()
    otp_input = driver.find_element(*VKID_OTP_INPUT)
    otp_input.clear()
    otp_input.send_keys(code)

    submits = driver.find_elements(*VKID_OTP_SUBMIT)
    submits_alt = driver.find_elements(*VKID_OTP_SUBMIT_ALT)

    if submits:
        submits[0].click()
    elif submits_alt:
        submits_alt[0].click()
    else:
        raise RuntimeError("no confirm otp button found")

    try:
        WebDriverWait(driver, 2).until(
            expected_conditions.presence_of_element_located(
                (By.CSS_SELECTOR, ".vkc__TextField__errorMessage")
            )
        )
        retry_code(driver, totp)
    except TimeoutException:
        return


def fill_in_password(driver: WebDriver, password: str):
    WebDriverWait(driver, 10).until(
        expected_conditions.presence_of_element_located(VKID_PASSWORD_INPUT)
    )

    driver.find_element(*VKID_PASSWORD_INPUT).send_keys(password)
    driver.find_element(*VKID_PASSWORD_SUBMIT).submit()


def auth(driver: WebDriver, phone: str, password: str, totp: TOTP):
    driver.get("https://m.vk.com/join?vkid_auth_type=sign_in")

    WebDriverWait(driver, 60).until(
        expected_conditions.presence_of_element_located(VKID_PHONE_INPUT)
    )

    driver.find_element(*VKID_PHONE_INPUT).send_keys(phone)
    driver.find_element(*VKID_PHONE_SUBMIT).click()

    try:
        retry_code(driver, totp)
        fill_in_password(driver, password)
    except TimeoutException:
        fill_in_password(driver, password)
        retry_code(driver, totp)

    driver.implicitly_wait(1)

    WebDriverWait(driver, 60).until(
        expected_conditions.url_matches("https://m.vk.com/feed")
    )


class Comment:
    comment_id: int = -1
    target_group_id: Optional[int] = None
    group_id: Optional[int] = None
    post_id: Optional[int] = None
    author_id: int
    comment_vk_id: Optional[int] = None
    posted_on: datetime.datetime
    text: Optional[str] = None
    attachments: list[str] = []


def parse_datetime(datetime_str):
    now = datetime.datetime.now()

    if "today" in datetime_str:
        datetime_str = datetime_str.replace("today", now.strftime("%d %b"))
    elif "yesterday" in datetime_str:
        yesterday = now - datetime.timedelta(days=1)
        datetime_str = datetime_str.replace("yesterday", yesterday.strftime("%d %b"))

    return parser.parse(datetime_str)


def get_all_comments(group_id: int) -> list[Comment]:
    target_url = f"https://vk.com/club{group_id}?act=event_log&action_type=wall&end_date=1-01-2038&mode=1&start_date=1-01-2017"

    if browser.current_url == target_url:
        browser.refresh()
    else:
        browser.get(target_url)

    try:
        WebDriverWait(browser, 10).until(expected_conditions.url_to_be(target_url))
    except (TimeoutException, TypeError):
        return get_all_comments(group_id)

    if browser.find_elements(
        By.XPATH,
        "//*[contains(text(), 'Internal server error. Please try again later')]",
    ):
        time.sleep(30)
        return get_all_comments(group_id)

    html = browser.page_source

    soup = BeautifulSoup(html, "html.parser")
    event_log_items = soup.select(".groups_edit_event_log_item")

    comments = []

    for item in event_log_items:
        title_element = item.select_one(".groups_edit_event_log_item_title")
        if not title_element or title_element.get_text(strip=True) not in [
            "Comment as community",
            "Wall management",
        ]:
            continue

        comment = Comment()

        admin_element = item.select_one(".groups_edit_event_log_item_labeled .mem_link")
        if admin_element and "mention_id" in admin_element.attrs:
            comment.author_id = int(admin_element["mention_id"].replace("id", ""))

        content_element = item.select_one(
            ".wall_reply_text, .wall_module .wall_post_text"
        )

        if content_element:
            comment.text = content_element.get_text(strip=True)

        stickers = item.select(".sticker_img_wrapper img")

        comment.attachments = [img["src"] for img in stickers if img.has_attr("src")]

        image_elements = item.select(".page_post_thumb_wrap")
        for img_elem in image_elements:
            style = img_elem.get("style", "")
            match = re.search(r"background-image: url\((.*?)\);", style)
            if match:
                image_url = match.group(1)
                comment.attachments.append(image_url)

        datetime_element = item.select_one(".groups_edit_event_log_item_date")
        if datetime_element:
            datetime_str = datetime_element.get_text(strip=True)
            comment.posted_on = parse_datetime(datetime_str)

        link_element = item.select_one(
            ".groups_edit_event_log_item_row a[href^='https://vk.com/wall-']"
        )

        if link_element:
            href = link_element.get("href", "")
            match_reply = re.search(r"reply=(\d+)", href)
            match_group = re.search(r"wall-([0-9]+)_", href)
            match_post = re.search(r"wall-\d+_(\d+)", href)
            if match_reply:
                comment.comment_vk_id = int(match_reply.group(1))
            if match_group:
                comment.target_group_id = int(match_group.group(1))
            if match_post:
                comment.post_id = int(match_post.group(1))

        comment.group_id = group_id

        if comment.comment_vk_id:
            comments.append(comment)

    return comments


def main():
    filename = f"scripts_results/comments/{SESSION_NAME}.json"
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    def add_comments(comments_to_add: list[Comment]):
        vars_to_add = [vars(i) for i in comments_to_add]

        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                existing_content = json.loads(f.read())
                existing_content.extend(vars_to_add)
        else:
            existing_content = vars_to_add

        with open(filename, "w", encoding="utf-8") as f:
            existing_content = json.dumps(
                existing_content,
                indent=4,
                sort_keys=True,
                default=str,
                ensure_ascii=False,
            )
            f.write(existing_content)

    auth(browser, PHONE, PASSWORD, TOTP)

    for group_id in GROUPS:
        add_comments(get_all_comments(group_id))

    browser.execute_script(
        'browserstack_executor: {"action": "setSessionStatus", "arguments": {"status":"passed", "reason": "success"}}'
    )


try:
    main()
except Exception as e:
    message = str(e)
    browser.execute_script(
        'browserstack_executor: {"action": "setSessionStatus", "arguments": {"status":"failed", "reason": '
        + json.dumps(message)
        + "}}"
    )
finally:
    browser.quit()
