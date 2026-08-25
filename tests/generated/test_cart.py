import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_add_single_product_to_cart(page: Page) -> None:
    # Step 1: Navigate to the product detail page of an available item
    await page.goto("http://localhost:3000/product/1")

    # Step 2: Click the 'Add to Cart' button
    add_to_cart_button = page.get_by_role("button", name="Add to Cart")
    await expect(add_to_cart_button).to_be_visible()
    await add_to_cart_button.click()

    # Step 3: Navigate to the shopping cart page
    cart_nav_link = page.get_by_role("link", name="Cart")
    await cart_nav_link.click()
    await expect(page).to_have_url("http://localhost:3000/cart")

    # Step 4: Verify that the selected product is displayed in the cart
    cart_item = page.locator(".cart-item").first
    await expect(cart_item).to_be_visible()

    # Step 5: Verify that the item quantity in the cart is 1
    quantity_input = cart_item.locator("input[name='quantity'], .quantity-value")
    await expect(quantity_input).to_have_value("1")
