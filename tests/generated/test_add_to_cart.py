import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_add_sauce_labs_backpack_to_cart(page: Page) -> None:
    await page.goto("https://www.saucedemo.com/inventory.html")
    product = page.locator("[data-test='inventory-item-name']").filter(has_text="Sauce Labs Backpack")
    await expect(product).to_be_visible()
    await page.locator("[data-test='add-to-cart-sauce-labs-backpack']").click()
    badge = page.locator("[data-test='shopping-cart-badge']")
    await expect(badge).to_have_text("1")
    await page.locator("[data-test='shopping-cart-link']").click()
    await expect(page).to_have_url("https://www.saucedemo.com/cart.html")
    cart_item = page.locator("[data-test='inventory-item-name']").filter(has_text="Sauce Labs Backpack")
    await expect(cart_item).to_be_visible()
    quantity = page.locator("[data-test='item-quantity']")
    await expect(quantity).to_have_text("1")