import os
import json

import pyotp
from selenium import webdriver
from selenium.common import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

DRIVER_PATH = os.environ.get("DRIVER_PATH")

TOTP = pyotp.TOTP(os.environ.get("VK_OTP"))
PHONE = os.environ.get("VK_USERNAME")
PASSWORD = os.environ.get("VK_PASSWORD")
GROUPS_WITH_LINKS = [int(i) for i in os.environ.get("GROUPS_WITH_LINKS").split(",")]
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


def switch_site(group_id: int) -> bool:
    element_dashboard_select = (By.CSS_SELECTOR, "div.Dashboard__statusSelect")
    element_status_placeholder = (By.CSS_SELECTOR, "div.Select__placeholder")
    element_selectable = (By.CSS_SELECTOR, "div.Select__option")

    target_url = f"https://vk.com/club{group_id}?act=site"

    browser.get(target_url)

    WebDriverWait(browser, 10).until(expected_conditions.url_to_be(target_url))

    try:
        WebDriverWait(browser, 2).until(
            expected_conditions.presence_of_element_located(element_dashboard_select)
        )
    except TimeoutException:
        return False

    browser.implicitly_wait(1)

    try:
        site_activation_status = browser.find_element(*element_dashboard_select)
    except NoSuchElementException:
        return False

    status_placeholder = site_activation_status.find_element(
        *element_status_placeholder
    )

    if status_placeholder.text != "Active":
        return False

    site_activation_status.click()

    WebDriverWait(browser, 60).until(
        expected_conditions.presence_of_element_located(element_selectable)
    )

    all_selectable = browser.find_elements(*element_selectable)

    for selectable in all_selectable:
        if selectable.text == "Disabled":
            selectable.click()
            return True

    return False


def main():
    auth(browser, PHONE, PASSWORD, TOTP)
    statuses: dict[int, bool] = {}

    for group_id in GROUPS_WITH_LINKS:
        statuses[group_id] = switch_site(group_id)

    filename = f"scripts_results/vk_link/{SESSION_NAME}.json"
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, "w") as f:
        content = json.dumps(
            statuses, indent=4, sort_keys=True, default=str, ensure_ascii=False
        )
        f.write(content)

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
