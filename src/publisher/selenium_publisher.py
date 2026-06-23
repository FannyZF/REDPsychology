import os
import time
import random
from pathlib import Path
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from src.utils.logger import get_logger

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).parent.parent.parent
PROFILE_DIR = ROOT_DIR / "data" / "chrome_profile"
SCREENSHOT_DIR = ROOT_DIR / "output" / "screenshots"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

CREATOR_URL = "https://creator.xiaohongshu.com"
PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"
LOGIN_URL = "https://creator.xiaohongshu.com/login"


class XiaohongshuPublisher:
    def __init__(self, profile_dir: str | None = None, headless: bool = True):
        self.profile_dir = str(profile_dir or PROFILE_DIR)
        self.headless = headless
        self.driver: webdriver.Chrome | None = None
        self.wait: WebDriverWait | None = None

    def _build_options(self) -> webdriver.ChromeOptions:
        opts = webdriver.ChromeOptions()
        opts.add_argument(f"--user-data-dir={self.profile_dir}")

        if self.headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--window-size=1920,1080")

        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-infobars")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)

        opts.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        return opts

    def start(self):
        logger.info("Starting browser...")
        opts = self._build_options()
        self.driver = webdriver.Chrome(options=opts)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self.wait = WebDriverWait(self.driver, 30)
        logger.info("Browser started")

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self.wait = None
            logger.info("Browser closed")

    def _screenshot(self, name: str):
        if not self.driver:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOT_DIR / f"{ts}_{name}.png"
        self.driver.save_screenshot(str(path))
        logger.info(f"Screenshot: {path}")

    def _random_delay(self, min_s: float = 0.5, max_s: float = 2.0):
        time.sleep(random.uniform(min_s, max_s))

    def _find_clickable(self, xpaths: list[str], timeout: int = 15,
                        description: str = "element") -> bool:
        for xp in xpaths:
            try:
                el = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((By.XPATH, xp))
                )
                self._random_delay(0.3, 0.8)
                el.click()
                logger.debug(f"Clicked {description}: {xp}")
                return True
            except (TimeoutException, NoSuchElementException):
                continue
        logger.warning(f"Could not find clickable {description}")
        return False

    def _find_and_send_keys(self, xpaths: list[str], text: str,
                            timeout: int = 15, description: str = "input") -> bool:
        for xp in xpaths:
            try:
                el = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, xp))
                )
                self._random_delay(0.3, 0.8)
                el.click()
                self._random_delay(0.2, 0.5)
                el.clear()
                el.send_keys(text)
                logger.debug(f"Filled {description}: {xp}")
                return True
            except (TimeoutException, NoSuchElementException):
                continue
        logger.warning(f"Could not find {description}")
        return False

    def _wait_for_upload(self, timeout: int = 300):
        for _ in range(timeout // 5):
            time.sleep(5)
            try:
                self.driver.find_element(By.XPATH, "//*[contains(text(), '上传成功') or contains(text(), '处理中')]")
            except NoSuchElementException:
                pass
            try:
                progress_els = self.driver.find_elements(
                    By.XPATH, "//*[contains(@class, 'progress') or contains(@class, 'upload')]"
                )
                if not progress_els:
                    return True
            except Exception:
                pass
        logger.warning("Upload wait timeout")

    def ensure_login(self) -> bool:
        self.driver.get(CREATOR_URL)
        self._random_delay(2, 4)

        page_source = self.driver.page_source.lower()
        login_indicators = ["login", "登录", "扫码", "qr", "sign"]
        is_login_page = any(ind in page_source for ind in login_indicators)

        if not is_login_page:
            try:
                self.driver.find_element(By.XPATH, "//*[contains(text(), '发布笔记')]")
                logger.info("Already logged in (Cookie valid)")
                self._screenshot("logged_in")
                return True
            except NoSuchElementException:
                pass

        logger.info("Not logged in. Opening login page...")
        self.driver.get(LOGIN_URL)
        self._random_delay(3, 5)
        self._screenshot("login_page")

        logger.info("Waiting for QR code scan (check screenshots)...")
        for i in range(24):
            time.sleep(5)
            try:
                self.driver.find_element(By.XPATH, "//*[contains(text(), '发布笔记')]")
                logger.info("Login successful!")
                self._screenshot("login_success")
                return True
            except NoSuchElementException:
                if i % 6 == 5:
                    logger.info(f"Still waiting for login... ({(i + 1) * 5}s)")
        return False

    def publish_video_note(self, video_path: str, title: str,
                           content: str, tags: list[str]) -> bool:
        if not self.driver:
            logger.error("Browser not started")
            return False

        logger.info(f"Publishing video note: {title[:30]}...")
        self._screenshot("before_publish")

        # Step 1: Navigate to publish page
        self.driver.get(PUBLISH_URL)
        self._random_delay(3, 5)

        # Step 2: Click upload video button
        upload_xpaths = [
            "//span[contains(text(), '上传视频')]/..",
            "//div[contains(text(), '上传视频')]/..",
            "//button[contains(text(), '上传')]",
            "//input[@type='file']",
            "//*[contains(@class, 'upload')]//input",
        ]
        for xp in upload_xpaths:
            try:
                el = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, xp))
                )
                if el.tag_name == "input" and el.get_attribute("type") == "file":
                    el.send_keys(str(Path(video_path).resolve()))
                    logger.info("Video file selected")
                    break
                else:
                    el.click()
                    self._random_delay(1, 2)
                    file_inputs = self.driver.find_elements(
                        By.XPATH, "//input[@type='file']"
                    )
                    if file_inputs:
                        file_inputs[0].send_keys(
                            str(Path(video_path).resolve())
                        )
                        logger.info("Video file selected via click")
                        break
                    else:
                        logger.warning("No file input found after click")
            except (TimeoutException, NoSuchElementException):
                continue

        # Wait for video upload to complete
        logger.info("Waiting for video upload...")
        self._wait_for_upload(timeout=300)
        self._random_delay(2, 4)
        self._screenshot("video_uploaded")

        # Step 3: Fill title
        title_xpaths = [
            "//input[@placeholder and contains(@placeholder, '标题')]",
            "//input[contains(@class, 'title')]",
            "//*[contains(@placeholder, '标题')]//input",
            "//input[@placeholder]",
        ]
        self._find_and_send_keys(title_xpaths, title, description="title input")
        self._random_delay(1, 2)

        # Step 4: Fill content/description - use JS for contenteditable
        desc = content
        if tags:
            desc += "\n\n" + " ".join(f"#{t}" for t in tags)

        desc_xpaths = [
            "//div[@contenteditable='true']",
            "//div[contains(@class, 'ql-editor')]",
            "//div[@role='textbox']",
        ]
        filled = False
        for xp in desc_xpaths:
            try:
                el = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, xp))
                )
                self._random_delay(0.3, 0.8)
                el.click()
                self._random_delay(0.3, 0.5)
                escaped = desc.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "<br>")
                self.driver.execute_script(f"arguments[0].innerHTML = '{escaped}'", el)
                self.driver.execute_script(
                    "arguments[0].dispatchEvent(new Event('input', {bubbles: true}))", el
                )
                logger.info(f"Filled description via JS")
                filled = True
                break
            except (TimeoutException, NoSuchElementException):
                continue

        if not filled:
            self._find_and_send_keys(
                ["//textarea[@placeholder]", "//textarea"],
                desc, description="description"
            )
        self._random_delay(1, 2)

        self._screenshot("filled_content")

        # Step 5: Click publish
        publish_xpaths = [
            "//span[contains(text(), '发布')]/..",
            "//button[contains(text(), '发布')]",
            "//div[contains(text(), '发布')]/..",
            "//*[@type='submit' and contains(., '发布')]",
        ]
        if self._find_clickable(publish_xpaths, description="publish button"):
            logger.info("Published successfully!")
            self._random_delay(3, 5)
            self._screenshot("published")
            return True

        logger.error("Failed to click publish button")
        self._screenshot("publish_failed")
        return False

    def publish_image_note(self, title: str, content: str, tags: list[str]) -> bool:
        if not self.driver:
            logger.error("Browser not started")
            return False

        logger.info(f"Publishing image note: {title[:30]}...")
        self.driver.get(PUBLISH_URL)
        self._random_delay(3, 5)

        desc = content
        if tags:
            desc += "\n\n" + " ".join(f"#{t}" for t in tags)

        title_xpaths = [
            "//input[@placeholder and contains(@placeholder, '标题')]",
            "//input[contains(@class, 'title')]",
            "//input[@placeholder]",
        ]
        desc_xpaths = [
            "//textarea[@placeholder and contains(@placeholder, '正文')]",
            "//div[@contenteditable='true']",
            "//textarea",
        ]
        self._find_and_send_keys(title_xpaths, title, description="title")
        self._random_delay(1, 2)
        self._find_and_send_keys(desc_xpaths, desc, description="description")
        self._random_delay(1, 2)

        publish_xpaths = [
            "//span[contains(text(), '发布')]/..",
            "//button[contains(text(), '发布')]",
            "//div[contains(text(), '发布')]/..",
        ]
        if self._find_clickable(publish_xpaths, description="publish button"):
            logger.info("Image note published!")
            self._random_delay(3, 5)
            return True

        return False
