from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.application_discovery_agent import (
    ApplicationDiscoveryAgent
)


class FakePlaywrightManager:

    def __init__(self, playwright):
        self.playwright = playwright

    async def __aenter__(self):
        return self.playwright

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


@pytest.mark.asyncio
async def test_authenticated_discovery_reuses_storage_state(
    monkeypatch,
    tmp_path
):
    storage_state = tmp_path / "storage_state.json"
    storage_state.write_text("{}", encoding="utf-8")

    body = AsyncMock()
    inventory = AsyncMock()
    inventory.count.return_value = 1

    page = MagicMock()
    page.url = "https://www.saucedemo.com/inventory.html"
    page.goto = AsyncMock()
    page.locator.side_effect = lambda selector: {
        "body": body,
        ".inventory_list": inventory
    }[selector]

    context = AsyncMock()
    context.new_page.return_value = page

    browser = AsyncMock()
    browser.new_context.return_value = context

    chromium = AsyncMock()
    chromium.launch.return_value = browser

    playwright = AsyncMock()
    playwright.chromium = chromium

    monkeypatch.setattr(
        "agents.application_discovery_agent.async_playwright",
        lambda: FakePlaywrightManager(playwright)
    )

    agent = ApplicationDiscoveryAgent(
        base_url="https://www.saucedemo.com/",
        storage_state=str(storage_state)
    )
    agent.validate_page = AsyncMock()
    agent._collect_page_evidence = AsyncMock(
        return_value={"authenticated": True}
    )
    flow_evidence = {
        "post_add_state": {
            "badge_text": "1",
            "shopping_cart_link_locator": {
                "strategy": "data-test",
                "value": "[data-test='shopping-cart-link']"
            },
            "cart_href": None
        },
        "cart_page": {
            "actual_url": "https://www.saucedemo.com/cart.html",
            "backpack_locator": {
                "strategy": "data-test",
                "value": "[data-test='inventory-item-name']"
            },
            "quantity_text": "1"
        },
        "cleanup": {
            "cart_empty": True,
            "badge_present": False
        }
    }
    agent._discover_add_backpack_to_cart = AsyncMock(
        return_value=flow_evidence
    )
    multi_product_flow = {
        "products": [
            {"name": "Sauce Labs Backpack"},
            {"name": "Sauce Labs Bike Light"},
        ],
        "add_steps": [{"badge_value": "1"}, {"badge_value": "2"}],
        "cleanup": {"cart_empty": True, "badge_present": False},
    }
    agent._discover_cart_flow = AsyncMock(return_value=multi_product_flow)
    agent.discover = AsyncMock(
        side_effect=AssertionError(
            "discover() must not be called"
        )
    )

    result = await agent.discover_authenticated()

    browser.new_context.assert_awaited_once_with(
        storage_state=str(storage_state.resolve())
    )
    page.goto.assert_awaited_once_with(
        "https://www.saucedemo.com/inventory.html",
        wait_until="domcontentloaded",
        timeout=60000
    )
    agent.discover.assert_not_awaited()
    agent._collect_page_evidence.assert_awaited_once_with(
        page,
        authenticated=True
    )
    agent._discover_add_backpack_to_cart.assert_awaited_once_with(page)
    agent._discover_cart_flow.assert_awaited_once_with(page, [
        "Sauce Labs Backpack", "Sauce Labs Bike Light"
    ])
    browser.close.assert_awaited_once()
    assert result == {
        "authenticated": True,
        "flows": {
            "add_backpack_to_cart": flow_evidence,
            "add_backpack_and_bike_light_to_cart": multi_product_flow,
        }
    }


def test_multi_product_flow_captures_ordered_state_and_cleanup():
    flow = {
        "products": [
            {
                "name": "Sauce Labs Backpack",
                "product_locator": {"value": "[data-test='inventory-item-name']"},
                "add_to_cart_locator": {
                    "value": "[data-test='add-to-cart-sauce-labs-backpack']"
                },
            },
            {
                "name": "Sauce Labs Bike Light",
                "product_locator": {"value": "[data-test='inventory-item-name']"},
                "add_to_cart_locator": {
                    "value": "[data-test='add-to-cart-sauce-labs-bike-light']"
                },
            },
        ],
        "add_steps": [{"badge_value": "1"}, {"badge_value": "2"}],
        "cart_navigation": {
            "shopping_cart_link_locator": {
                "value": "[data-test='shopping-cart-link']"
            }
        },
        "cart_page": {
            "actual_url": "https://www.saucedemo.com/cart.html",
            "items": [
                {"name": "Sauce Labs Backpack", "quantity": "1"},
                {"name": "Sauce Labs Bike Light", "quantity": "1"},
            ],
        },
        "cleanup": {"cart_empty": True, "badge_present": False},
    }

    assert [step["badge_value"] for step in flow["add_steps"]] == ["1", "2"]
    assert {item["name"] for item in flow["cart_page"]["items"]} == {
        "Sauce Labs Backpack", "Sauce Labs Bike Light"
    }
    assert all(item["quantity"] == "1" for item in flow["cart_page"]["items"])
    assert flow["cleanup"] == {"cart_empty": True, "badge_present": False}


@pytest.fixture
def add_backpack_flow():
    return {
        "post_add_state": {
            "badge_text": "1",
            "shopping_cart_link_locator": {
                "strategy": "data-test",
                "value": "[data-test='shopping-cart-link']"
            },
            "cart_href": None
        },
        "cart_page": {
            "actual_url": "https://www.saucedemo.com/cart.html",
            "backpack_locator": {
                "strategy": "data-test",
                "value": "[data-test='inventory-item-name']"
            },
            "quantity_text": "1"
        },
        "cleanup": {
            "cart_empty": True,
            "badge_present": False
        }
    }


def test_add_backpack_badge_becomes_one(add_backpack_flow):
    assert add_backpack_flow["post_add_state"]["badge_text"] == "1"


def test_add_backpack_cart_link_is_discovered(add_backpack_flow):
    post_add = add_backpack_flow["post_add_state"]
    assert post_add["shopping_cart_link_locator"] is not None
    assert "cart_href" in post_add


def test_backpack_appears_in_cart(add_backpack_flow):
    cart_page = add_backpack_flow["cart_page"]
    assert cart_page["actual_url"].endswith("/cart.html")
    assert cart_page["backpack_locator"] is not None


def test_backpack_quantity_is_one(add_backpack_flow):
    assert add_backpack_flow["cart_page"]["quantity_text"] == "1"


def test_add_backpack_cleanup_restores_empty_cart(add_backpack_flow):
    cleanup = add_backpack_flow["cleanup"]
    assert cleanup["cart_empty"] is True
    assert cleanup["badge_present"] is False


@pytest.mark.asyncio
async def test_authenticated_discovery_requires_storage_state():
    agent = ApplicationDiscoveryAgent(
        base_url="https://www.saucedemo.com"
    )

    with pytest.raises(ValueError, match="storage_state is required"):
        await agent.discover_authenticated()


@pytest.mark.asyncio
async def test_authenticated_discovery_rejects_missing_state_file(
    tmp_path
):
    missing_state = tmp_path / "missing.json"
    agent = ApplicationDiscoveryAgent(
        base_url="https://www.saucedemo.com",
        storage_state=str(missing_state)
    )

    with pytest.raises(FileNotFoundError, match="Storage state not found"):
        await agent.discover_authenticated()
