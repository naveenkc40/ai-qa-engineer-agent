import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_successfully_add_sauce_labs_backpack_to_cart(page: Page) -> None:
    await page.goto("https://www.saucedemo.com/inventory.html")
    backpack = page.locator("[data-test='inventory-item-name']", has_text="Sauce Labs Backpack")
    await expect(backpack).to_be_visible()
    await page.locator("[data-test='add-to-cart-sauce-labs-backpack']").click()
    cart_badge = page.locator("[data-test='shopping-cart-badge']")
    await expect(cart_badge).to_have_text("1")
    await page.locator("[data-test='shopping-cart-link']").click()
    await expect(page).to_have_url("https://www.saucedemo.com/cart.html")
    cart_item_name = page.locator("[data-test='inventory-item-name']")
    await expect(cart_item_name).to_have_text("Sauce Labs Backpack")
    cart_quantity = page.locator("[data-test='item-quantity']")
    await expect(cart_quantity).to_have_text("1")
