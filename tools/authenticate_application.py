import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


BASE_URL = "https://www.saucedemo.com/"

USERNAME = "standard_user"
PASSWORD = "secret_sauce"

STORAGE_STATE = (
    "application_context/storage_state.json"
)


async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context()

        page = await context.new_page()

        print(
            f"Opening: {BASE_URL}"
        )

        await page.goto(
            BASE_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        print("Logging in...")

        await page.get_by_role(
            "textbox",
            name="Username"
        ).fill(USERNAME)

        await page.get_by_role(
            "textbox",
            name="Password"
        ).fill(PASSWORD)

        await page.get_by_role(
            "button",
            name="Login"
        ).click()

        # Wait for the application to navigate.
        await page.wait_for_url(
            "**/inventory.html",
            timeout=30000
        )

        print(
            f"Authenticated URL: {page.url}"
        )

        # ------------------------------------------------
        # AUTHENTICATION VALIDATION
        # ------------------------------------------------

        if "/inventory.html" not in page.url:

            raise RuntimeError(
                "Authentication failed: "
                f"unexpected URL {page.url}"
            )

        inventory = page.locator(
            ".inventory_list"
        )

        if await inventory.count() == 0:

            raise RuntimeError(
                "Authentication failed: "
                "inventory page was not detected."
            )

        products = page.locator(
            ".inventory_item"
        )

        product_count = await products.count()

        if product_count == 0:

            raise RuntimeError(
                "Authentication failed: "
                "no products were detected."
            )

        print(
            f"✓ Authentication verified"
        )

        print(
            f"✓ Inventory products: "
            f"{product_count}"
        )

        # ------------------------------------------------
        # SAVE AUTHENTICATED STATE
        # ------------------------------------------------

        Path(
            "application_context"
        ).mkdir(
            parents=True,
            exist_ok=True
        )

        await context.storage_state(
            path=STORAGE_STATE
        )

        print(
            f"✓ Storage state saved to:"
            f"\n{STORAGE_STATE}"
        )

        # ------------------------------------------------
        # VERIFY SAVED STATE
        # ------------------------------------------------

        state = json.loads(
            Path(STORAGE_STATE).read_text()
        )

        print(
            "\nStorage state summary:"
        )

        print(
            f"Cookies: "
            f"{len(state.get('cookies', []))}"
        )

        print(
            f"Origins: "
            f"{len(state.get('origins', []))}"
        )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())