import asyncio

from playwright.async_api import async_playwright


async def main():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            storage_state=(
                "application_context/"
                "storage_state.json"
            )
        )

        page = await context.new_page()

        print(
            "\nOpening inventory page..."
        )

        await page.goto(
            "https://www.saucedemo.com/inventory.html",
            wait_until="domcontentloaded",
            timeout=60000
        )

        print(
            "\nRequested URL:"
        )
        print(
            "https://www.saucedemo.com/inventory.html"
        )

        print("\nActual URL:")
        print(page.url)

        print("\nTitle:")
        print(await page.title())

        print("\nPage text:")
        print(
            (await page.locator("body").inner_text())[:2000]
        )

        print("\nStorage state cookies:")

        state = await context.storage_state()

        for cookie in state["cookies"]:
            print(
                f"{cookie['name']} "
                f"domain={cookie['domain']} "
                f"path={cookie['path']}"
            )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())