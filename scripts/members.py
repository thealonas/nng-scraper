import datetime
import json
import os
import time
from typing import Optional

import pyotp
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
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

WRAP_PARENT = (By.CSS_SELECTOR, ".groups_edit_event_log_item_wrap")
WRAP_NAME = (By.CSS_SELECTOR, ".groups_edit_event_log_item_title")
WRAP_CONTROL = (By.CSS_SELECTOR, "a.groups_edit_event_log_item_wrap_toggle")

LOG_ITEM_PARENT = (By.CSS_SELECTOR, ".groups_edit_event_log_item")


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


def unwrap_all_items():
    all_wraps = browser.find_elements(*WRAP_PARENT)

    for wrap in all_wraps:
        name = next(iter(wrap.find_elements(*WRAP_NAME)), "")
        if name.text != "Member administration":
            continue

        wrap.find_element(*WRAP_CONTROL).click()
        time.sleep(0.3)


def cancel_all_kicks(group_id: int) -> list[int]:
    target_url = f"https://vk.com/club{group_id}?act=event_log&action_type=users&end_date=1-01-2038&mode=1&role=editors&start_date=1-01-2017"

    if browser.current_url == target_url:
        browser.refresh()
    else:
        browser.get(target_url)

    try:
        WebDriverWait(browser, 10).until(expected_conditions.url_to_be(target_url))
    except (TimeoutException, TypeError):
        return cancel_all_kicks(group_id)

    unwrap_all_items()

    action_links = browser.find_elements(
        By.CSS_SELECTOR, "a.groups_edit_event_log_item_action_link"
    )

    admin_ids = []

    for action_link in action_links:
        parent_div = action_link.find_element(
            By.XPATH, "./ancestor::div[contains(@class, 'groups_edit_event_log_item')]"
        )

        admin_link = parent_div.find_element(
            By.XPATH,
            ".//div[contains(@class,'groups_edit_event_log_item_label') and contains(text(), 'Administrator')]/following-sibling::div[contains(@class, 'groups_edit_event_log_item_labeled')]//a[contains(@class, 'mem_link')]",
        )

        admin_id = admin_link.get_attribute("href").split("id")[-1]
        admin_ids.append(int(admin_id))

        webdriver.ActionChains(browser).move_to_element(action_link).click(
            action_link
        ).perform()

        WebDriverWait(browser, 10).until(expected_conditions.staleness_of(action_link))
        time.sleep(30)

    return admin_ids


def main():
    filename = f"scripts_results/members/{SESSION_NAME}.json"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    auth(browser, PHONE, PASSWORD, TOTP)

    groups_and_intruders: dict[int, list[int]] = {}

    for group_id in GROUPS:
        groups_and_intruders[group_id] = list(set(cancel_all_kicks(group_id)))

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(groups_and_intruders, f)

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
