import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_add_backpack_and_bike_light_to_cart(page: Page) -> None:
    await page.goto("https://www.saucedemo.com/inventory.html")
    await expect(page.locator("[data-test='inventory-item-name']", has_text="Sauce Labs Backpack")).to_be_visible()
    await expect(page.locator("[data-test='inventory-item-name']", has_text="Sauce Labs Bike Light")).to_be_visible()
    await page.locator("[data-test='add-to-cart-sauce-labs-backpack']").click()
    await page.locator("[data-test='add-to-cart-sauce-labs-bike-light']").click()
    await expect(page.locator("[data-test='shopping-cart-badge']")).to_have_text("2")
    await page.locator("[data-test='shopping-cart-link']").click()
    await expect(page).to_have_url("https://www.saucedemo.com/cart.html")
    await expect(page.locator("[data-test='inventory-item-name']", has_text="Sauce Labs Backpack")).to_be_visible()
    await expect(page.locator("[data-test='inventory-item-name']", has_text="Sauce Labs Bike Light")).to_be_visible()
    quantities = page.locator("[data-test='item-quantity']")
    await expect(quantities.nth(0)).to_have_text("1")
    await expect(quantities.nth(1)).to_have_text("1")