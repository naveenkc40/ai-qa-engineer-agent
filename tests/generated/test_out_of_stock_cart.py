import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_add_out_of_stock_product_to_cart(page: Page) -> None:
    await page.goto("http://localhost:3000/products/out-of-stock-item")
    add_to_cart_button = page.get_by_role("button", name="Add to Cart")
    out_of_stock_label = page.get_by_text("Out of Stock", exact=False)
    if await add_to_cart_button.is_visible():
        await expect(add_to_cart_button).to_be_disabled()
    else:
        await expect(out_of_stock_label).to_be_visible()
    await page.goto("http://localhost:3000/cart")
    cart_items = page.locator(".cart-item, [data-testid='cart-item']")
    await expect(cart_items).to_have_count(0)