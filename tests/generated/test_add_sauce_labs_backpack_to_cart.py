import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_add_sauce_labs_backpack_to_cart(page: Page) -> None:
    await page.goto("https://www.saucedemo.com/inventory.html")
    add_to_cart_button = page.locator("[data-test='add-to-cart-sauce-labs-backpack']")
    await add_to_cart_button.click()
    cart_badge = page.locator("[data-test='shopping-cart-badge']")
    await expect(cart_badge).to_have_text("1")
    remove_button = page.locator("[data-test='remove-sauce-labs-backpack']")
    await expect(remove_button).to_be_visible()
