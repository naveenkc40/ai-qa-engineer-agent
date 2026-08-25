import asyncio
import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_rapid_consecutive_clicks_add_to_cart(page: Page):
    failed_responses = []

    def handle_response(response):
        if response.status >= 500:
            failed_responses.append((response.url, response.status))

    page.on("response", handle_response)

    await page.goto("http://localhost:3000/product/1")

    add_to_cart_button = page.get_by_role("button", name="Add to Cart")
    await expect(add_to_cart_button).to_be_visible()

    await asyncio.gather(*[add_to_cart_button.click(no_wait_after=True) for _ in range(5)])

    cart_link = page.get_by_role("link", name="Cart")
    await cart_link.click()

    await expect(page).to_have_url("http://localhost:3000/cart")

    quantity_element = page.locator("[data-testid='cart-item-quantity']").first
    await expect(quantity_element).to_be_visible()

    assert len(failed_responses) == 0, f"Server errors detected: {failed_responses}"