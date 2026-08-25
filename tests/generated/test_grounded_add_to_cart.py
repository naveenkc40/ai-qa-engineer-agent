"""Grounded SauceDemo example. Generation does not execute this test."""

import pytest
from playwright.async_api import Page, expect


@pytest.mark.asyncio
async def test_add_backpack_to_cart(page: Page):
    await page.goto("https://www.saucedemo.com/inventory.html")
    add_button = page.locator(
        "[data-test='add-to-cart-sauce-labs-backpack']"
    )
    await expect(add_button).to_be_visible()
    await expect(add_button).to_be_enabled()
    await add_button.click()
