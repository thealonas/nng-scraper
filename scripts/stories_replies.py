import json
import os
import time

import pyotp
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

DRIVER_PATH = os.environ.get("DRIVER_PATH")

TOTP = pyotp.TOTP(os.environ.get("VK_OTP"))
PHONE = os.environ.get("VK_USERNAME")
PASSWORD = os.environ.get("VK_PASSWORD")
GROUPS = [int(i) for i in os.environ.get("GROUPS").split(",")]
SESSION_NAME = os.environ.get("SESSION_NAME")

service = webdriver.ChromeService(executable_path=DRIVER_PATH)
browser = webdriver.Chrome(service=service)

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

GROUP_DIV = (By.CSS_SELECTOR, ".group_edit")
CHILD_REPLY_CLICKABLE_WRAP = (By.CSS_SELECTOR, ".idd_wrap")
CHILD_REPLY_SELECTED_VALUE = (By.CSS_SELECTOR, ".idd_selected_value")
CHILD_REPLY_BUTTON = (By.ID, "groups_edit_g_stories_replies_input")

CHILD_POPUP = (By.CSS_SELECTOR, ".idd_popup")
CHILD_POPUP_ITEM = (By.CSS_SELECTOR, ".idd_item")
CHILD_POPUP_ITEM_NAME = (By.CSS_SELECTOR, ".idd_item_name")

SAVE_BUTTON = (By.CSS_SELECTOR, "button.group_save_button")
SAVE_BUTTON_CHILDREN_CONTENT = (By.CSS_SELECTOR, "span.FlatButton__content")

UPLOAD_BUTTON_HOVER = (By.CSS_SELECTOR, ".page-cover-actions-btn")
UPLOAD_BUTTON_CLICK = (By.CSS_SELECTOR, ".page-group-action")

UPLOAD_DIV = (By.CSS_SELECTOR, ".groups_edit_cover_wrap_main_input")
UPLOAD_INPUT = (By.CSS_SELECTOR, "input[type=file]")


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

    check_for_auth_flood_control(driver)

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


def check_for_auth_flood_control(driver: WebDriver):
    try:
        WebDriverWait(driver, 2).until(
            expected_conditions.presence_of_element_located(
                (
                    By.XPATH,
                    "//*[contains(text(), 'Flood control')]",
                )
            )
        )
    except (TimeoutException, TypeError):
        pass
    else:
        time.sleep(10)
        return

    try:
        WebDriverWait(driver, 2).until(
            expected_conditions.presence_of_element_located(
                (
                    By.XPATH,
                    "//*[contains(text(), 'You have no more code input attempts left')]",
                )
            )
        )
    except (TimeoutException, TypeError):
        pass
    else:
        time.sleep(30)
        return


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

    time.sleep(1)

    WebDriverWait(driver, 10).until(
        expected_conditions.url_matches("https://m.vk.com/feed")
    )


def try_find_element(element: tuple[str, str]):
    all_elements = browser.find_elements(*element)
    return any(all_elements)


def go_to_group(group_id: int):
    target_url = f"https://vk.com/club{group_id}?act=stories_replies"
    if browser.current_url == target_url:
        browser.refresh()
    else:
        browser.get(target_url)

    try:
        WebDriverWait(browser, 10).until(expected_conditions.url_to_be(target_url))
    except (TimeoutException, TypeError):
        return


def replies_enabled() -> bool:
    group_div = browser.find_elements(*GROUP_DIV)
    if not group_div:
        return False

    current_value = group_div[0].find_element(*CHILD_REPLY_SELECTED_VALUE).text
    return current_value == "Enabled"


def press_save_button():
    all_buttons = browser.find_elements(*SAVE_BUTTON)
    for button in all_buttons:
        if button.find_element(*SAVE_BUTTON_CHILDREN_CONTENT).text != "Save":
            continue
        button.click()
        return


def disable_replies():
    WebDriverWait(browser, 10).until(
        expected_conditions.presence_of_element_located(GROUP_DIV)
    )

    group_div = browser.find_element(*GROUP_DIV)
    reply_wrap = group_div.find_element(*CHILD_REPLY_CLICKABLE_WRAP)
    reply_wrap.click()

    time.sleep(0.1)

    popup = browser.find_element(*CHILD_POPUP)
    items = popup.find_elements(*CHILD_POPUP_ITEM)
    for item in items:
        if item.find_element(*CHILD_POPUP_ITEM_NAME).text == "Disabled":
            item.click()
            break

    press_save_button()


def main():
    auth(browser, PHONE, PASSWORD, TOTP)

    for group in GROUPS:
        go_to_group(group)

        if not replies_enabled():
            continue

        disable_replies()

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
