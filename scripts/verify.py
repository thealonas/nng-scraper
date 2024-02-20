import json
import os
import time

import pyotp
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

DRIVER_PATH = os.environ.get("DRIVER_PATH")

TOTP = pyotp.TOTP(os.environ.get("VK_OTP"))
PHONE = os.environ.get("VK_USERNAME")
PASSWORD = os.environ.get("VK_PASSWORD")
USERS = [int(i) for i in os.environ.get("UNVERIFIED_USERS").split(",")]
SESSION_NAME = os.environ.get("SESSION_NAME")

service = webdriver.ChromeService(executable_path=DRIVER_PATH)

options = webdriver.ChromeOptions()
options.add_argument("--blink-settings=imagesEnabled=false")

browser = webdriver.Chrome(service=service, options=options)
browser.set_window_size(420, 932)

USER_AVATAR = (By.CLASS_NAME, "OwnerPageAvatar__underlay")

BLUE_CHECK_MARK = (By.CLASS_NAME, "ProfileInfoName__imageStatus--verified")

GRAY_CHECK_MARK = (By.CLASS_NAME, "ProfileInfoName__imageStatus--esia")

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

    WebDriverWait(driver, 10).until(
        expected_conditions.url_matches("https://m.vk.com/feed")
    )


def try_find_element(element: tuple[str, str]):
    all_elements = browser.find_elements(*element)
    return any(all_elements)


def has_service_message(text: str):
    all_service_messages = browser.find_elements(
        By.CSS_SELECTOR, "div.service_msg_null"
    )
    for service_message in all_service_messages:
        if text in service_message.text or service_message.text == text:
            return True

    return False


def is_verified(user_id: int) -> bool:
    target_url = f"https://m.vk.com/id{user_id}"

    if browser.current_url != target_url:
        browser.get(target_url)
    else:
        browser.refresh()

    try:
        WebDriverWait(browser, 15).until(expected_conditions.url_matches(target_url))
    except (TypeError, TimeoutException):
        return is_verified(user_id)

    try:
        WebDriverWait(browser, 15).until(
            expected_conditions.visibility_of_element_located(USER_AVATAR)
        )
    except TimeoutException:
        if has_service_message(
            "This page has either been deleted or not been created yet"
        ):
            return False

        if any(
            browser.find_elements(
                By.XPATH,
                "//*[contains(text(), 'You have tried to open several similar pages too fast')]",
            )
        ):
            time.sleep(60)
            return is_verified(user_id)

        raise

    time.sleep(1)

    return try_find_element(BLUE_CHECK_MARK) or try_find_element(GRAY_CHECK_MARK)


def main():
    auth(browser, PHONE, PASSWORD, TOTP)
    output = {}

    for user in USERS:
        output[user] = is_verified(user)

    filename = f"scripts_results/verify/{SESSION_NAME}.json"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        f.write(json.dumps(output))

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
