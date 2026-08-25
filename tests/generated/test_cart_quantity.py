import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_add_same_product_twice_increments_quantity(page: Page) -> None:
    await page.goto("http://localhost:3000/product/1")
    add_to_cart_button = page.get_by_role("button", name="Add to Cart")
    await add_to_cart_button.click()
    await add_to_cart_button.click()
    cart_link = page.get_by_role("link", name="Cart")
    if await cart_link.is_visible():
        await cart_link.click()
    else:
        await page.goto("http://localhost:3000/cart")
    cart_items = page.locator(".cart-item, [data-testid='cart-item']")
    await expect(cart_items).to_have_count(1)
    quantity_element = page.locator(".cart-item-quantity, [data-testid='quantity']")
    await expect(quantity_element).to_contain_text("2")