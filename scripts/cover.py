import json
import os
import time

import pyotp
from selenium import webdriver
from selenium.common import TimeoutException
from selenium.webdriver import Keys, ActionChains
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

COVER_LINK = "https://nng.alonas.lv/img/style/cover/png/editors.png"

DRIVER_PATH = os.environ.get("DRIVER_PATH")

TOTP = pyotp.TOTP(os.environ.get("VK_OTP"))
PHONE = os.environ.get("VK_USERNAME")
PASSWORD = os.environ.get("VK_PASSWORD")
GROUPS = [int(i) for i in os.environ.get("GROUPS").split(",")]
SESSION_NAME = os.environ.get("SESSION_NAME")

service = webdriver.ChromeService(executable_path=DRIVER_PATH)

options = webdriver.ChromeOptions()
options.add_extension("chrome_extensions/i_am_gentlemen.crx")

browser = webdriver.Chrome(service=service, options=options)
browser.set_window_size(980, 932)

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

COVER_ELEMENT = (By.CSS_SELECTOR, "div._page_cover")

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
    target_url = f"https://vk.com/club{group_id}"
    if browser.current_url == target_url:
        browser.refresh()
    else:
        browser.get(target_url)

    try:
        WebDriverWait(browser, 10).until(expected_conditions.url_to_be(target_url))
    except (TimeoutException, TypeError):
        return


def check_cover_exists(group_id: int) -> bool:
    go_to_group(group_id)

    try:
        WebDriverWait(browser, 1).until(
            expected_conditions.visibility_of_element_located(COVER_ELEMENT)
        )
    except (TimeoutException, TypeError):
        return False

    element = browser.find_element(*COVER_ELEMENT)
    style = element.get_property("style")

    if style and "background-image" in style:
        return True

    return False


def download_cover():
    browser.get(COVER_LINK)

    WebDriverWait(browser, 25).until(
        expected_conditions.presence_of_element_located((By.CSS_SELECTOR, "img"))
    )

    time.sleep(1)

    image = browser.find_element(By.CSS_SELECTOR, "img")

    actions = (
        ActionChains(browser)
        .move_to_element(image)
        .key_down(Keys.ALT)
        .click()
        .key_up(Keys.ALT)
    )

    actions.perform()

    time.sleep(1)


def press_confirm_button():
    all_buttons = browser.find_elements(
        By.CSS_SELECTOR, "button.vkuiButton--mode-primary"
    )

    for button in all_buttons:
        button_contents = button.find_elements(
            By.CSS_SELECTOR, "span.vkuiButton__content"
        )

        if not button_contents:
            continue

        try:
            required_button = button_contents[0].text == "Set cover"
            if not required_button:
                continue
            button.click()
        except Exception as e:
            print(e)
            continue


def upload_cover():
    browser.find_element(*UPLOAD_BUTTON_HOVER).click()

    all_buttons = browser.find_elements(*UPLOAD_BUTTON_CLICK)

    for button in all_buttons:
        if button.text != "Upload image":
            continue

        button.click()
        break

    time.sleep(5)

    browser.find_element(*UPLOAD_INPUT).send_keys(
        "C:/Users/hello/Downloads/editors.png"
    )

    time.sleep(5)

    press_confirm_button()


def main():
    download_cover()

    auth(browser, PHONE, PASSWORD, TOTP)

    for group in GROUPS:
        if not check_cover_exists(group):
            upload_cover()

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
