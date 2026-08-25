import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright


load_dotenv()


class AuthenticationAgent:

    def __init__(self, base_url: str):

        self.base_url = base_url

        self.username = os.getenv("QA_USERNAME")
        self.password = os.getenv("QA_PASSWORD")

        if not self.username:
            raise ValueError(
                "QA_USERNAME is missing from .env"
            )

        if not self.password:
            raise ValueError(
                "QA_PASSWORD is missing from .env"
            )

    async def login(self):

        async with async_playwright() as p:

            browser = await p.chromium.launch(
                headless=True
            )

            context = await browser.new_context()

            page = await context.new_page()

            print(
                f"Opening: {self.base_url}"
            )

            await page.goto(
                self.base_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            await page.locator("body").wait_for(
                state="visible",
                timeout=30000
            )

            print("Logging in...")

            await page.get_by_role(
                "textbox",
                name="Username"
            ).fill(self.username)

            await page.get_by_role(
                "textbox",
                name="Password"
            ).fill(self.password)

            await page.get_by_role(
                "button",
                name="Login"
            ).click()

            await page.wait_for_url(
                "**/inventory.html",
                timeout=30000
            )

            print(
                "✓ Authentication successful"
            )

            print(
                f"Authenticated URL: {page.url}"
            )

            storage_dir = Path(
                "application_context"
            )

            storage_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            storage_file = (
                storage_dir /
                "storage_state.json"
            )

            await context.storage_state(
                path=str(storage_file)
            )

            print(
                f"✓ Storage state saved: "
                f"{storage_file}"
            )

            await browser.close()