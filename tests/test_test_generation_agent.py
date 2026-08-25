import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents.requirement_agent import TestScenario as ScenarioModel
from agents.test_generation_agent import TestGenerationAgent as GenerationAgent


def scenario():
    return ScenarioModel(
        id="CART-001",
        title="Add Sauce Labs Backpack to cart",
        description="Add the evidenced product to the cart",
        scenario_type="positive",
        priority="high",
        steps=["Open inventory", "Add Sauce Labs Backpack to cart"],
        expected_result="The add-to-cart action completes",
    )


def multi_product_scenario():
    return ScenarioModel(
        id="CART-002",
        title="Add Sauce Labs Backpack and Sauce Labs Bike Light to cart",
        description="Add both named products and verify the cart",
        scenario_type="positive",
        priority="high",
        steps=["Open inventory", "Add both products", "Open cart"],
        expected_result="Both products have quantity 1 in the cart",
    )


def client_returning(payload):
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps(payload)
    )
    return client


def test_loads_authenticated_map_and_passes_evidence_to_llm(tmp_path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({
        "authenticated": True,
        "application": "SauceDemo",
        "base_url": "https://www.saucedemo.com",
        "page": {"url": "https://www.saucedemo.com/inventory.html"},
        "products": [], "cart": {}, "buttons": [], "links": [], "inputs": []
    }), encoding="utf-8")
    client = client_returning({
        "status": "cannot_generate", "grounded": False,
        "missing_evidence": ["No evidenced product locator"]
    })

    result = GenerationAgent(map_path, client=client).generate(scenario())

    prompt = client.models.generate_content.call_args.kwargs["contents"]
    assert "https://www.saucedemo.com/inventory.html" in prompt
    assert "Never invent or infer URLs" in prompt
    assert result.status == "cannot_generate"
    assert result.code == ""


def test_rejects_an_invented_selector():
    client = client_returning({
        "status": "generated",
        "filename": "test_cart.py",
        "test_name": "test_add_backpack",
        "code": "await page.locator('#invented').click()",
        "grounded": True,
        "evidence_used": ["page.url=https://www.saucedemo.com/inventory.html"],
        "missing_evidence": [],
    })

    result = GenerationAgent(client=client).generate(scenario())

    assert result.status == "cannot_generate"
    assert result.grounded is False
    assert "selector not in application map: #invented" in result.missing_evidence
    assert result.code == ""


def test_rejects_an_invented_asserted_url():
    client = client_returning({
        "status": "generated",
        "filename": "test_cart.py",
        "test_name": "test_add_backpack",
        "code": "await expect(page).to_have_url('https://www.saucedemo.com/invented')",
        "grounded": True,
        "evidence_used": ["page.url=https://www.saucedemo.com/inventory.html"],
        "missing_evidence": [],
    })

    result = GenerationAgent(client=client).generate(scenario())

    assert result.status == "cannot_generate"
    assert result.grounded is False
    assert "URL not in application map: https://www.saucedemo.com/invented" in result.missing_evidence


def test_accepts_grounded_saucedemo_add_to_cart_test():
    code = """import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_add_backpack_to_cart(page: Page):
    await page.goto(\"https://www.saucedemo.com/inventory.html\")
    add_button = page.locator(\"[data-test='add-to-cart-sauce-labs-backpack']\")
    await expect(add_button).to_be_visible()
    await expect(add_button).to_be_enabled()
    await add_button.click()
"""
    client = client_returning({
        "status": "generated",
        "filename": "test_grounded_add_to_cart.py",
        "test_name": "test_add_backpack_to_cart",
        "code": code,
        "grounded": True,
        "evidence_used": [
            "page.url=https://www.saucedemo.com/inventory.html",
            "products[0].name=Sauce Labs Backpack",
            "products[0].add_to_cart=True",
            "products[0].add_to_cart_data_test=add-to-cart-sauce-labs-backpack",
        ],
        "missing_evidence": [],
    })

    result = GenerationAgent(client=client).generate(scenario())

    assert result.status == "generated"
    assert result.grounded is True
    assert result.code == code


def test_generates_complete_backpack_flow_from_stateful_evidence(tmp_path):
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({
        "authenticated": True,
        "base_url": "https://www.saucedemo.com",
        "page": {"url": "https://www.saucedemo.com/inventory.html"},
        "products": [{"name": "Sauce Labs Backpack"}],
        "cart": {"cart_href": None},
        "flows": {"add_backpack_to_cart": {
            "preconditions": {
                "inventory_url": "https://www.saucedemo.com/inventory.html",
                "product_name": "Sauce Labs Backpack",
                "product_locator": {
                    "strategy": "data-test",
                    "value": "[data-test='inventory-item-name']",
                },
            },
            "action": {"locator": {
                "strategy": "data-test",
                "value": "[data-test='add-to-cart-sauce-labs-backpack']",
            }},
            "post_add_state": {
                "shopping_cart_badge_locator": {
                    "strategy": "data-test",
                    "value": "[data-test='shopping-cart-badge']",
                },
                "badge_text": "1",
                "shopping_cart_link_locator": {
                    "strategy": "data-test",
                    "value": "[data-test='shopping-cart-link']",
                },
            },
            "cart_page": {
                "actual_url": "https://www.saucedemo.com/cart.html",
                "backpack_locator": {
                    "strategy": "data-test",
                    "value": "[data-test='inventory-item-name']",
                },
                "quantity_locator": {
                    "strategy": "data-test",
                    "value": "[data-test='item-quantity']",
                },
                "quantity_text": "1",
            },
        }},
    }), encoding="utf-8")
    code = """import pytest
from playwright.async_api import Page, expect

@pytest.mark.asyncio
async def test_add_backpack_to_cart(page: Page):
    await page.goto(\"https://www.saucedemo.com/inventory.html\")
    await expect(page.locator(\"[data-test='inventory-item-name']\").first).to_have_text(\"Sauce Labs Backpack\")
    await page.locator(\"[data-test='add-to-cart-sauce-labs-backpack']\").click()
    await expect(page.locator(\"[data-test='shopping-cart-badge']\")).to_have_text(\"1\")
    await page.locator(\"[data-test='shopping-cart-link']\").click()
    await expect(page).to_have_url(\"https://www.saucedemo.com/cart.html\")
    await expect(page.locator(\"[data-test='inventory-item-name']\")).to_have_text(\"Sauce Labs Backpack\")
    await expect(page.locator(\"[data-test='item-quantity']\")).to_have_text(\"1\")
"""
    references = [
        "flows.add_backpack_to_cart.preconditions.inventory_url=https://www.saucedemo.com/inventory.html",
        "flows.add_backpack_to_cart.preconditions.product_name=Sauce Labs Backpack",
        "flows.add_backpack_to_cart.preconditions.product_locator.value=[data-test='inventory-item-name']",
        "flows.add_backpack_to_cart.action.locator.value=[data-test='add-to-cart-sauce-labs-backpack']",
        "flows.add_backpack_to_cart.post_add_state.shopping_cart_badge_locator.value=[data-test='shopping-cart-badge']",
        "flows.add_backpack_to_cart.post_add_state.badge_text=1",
        "flows.add_backpack_to_cart.post_add_state.shopping_cart_link_locator.value=[data-test='shopping-cart-link']",
        "flows.add_backpack_to_cart.cart_page.actual_url=https://www.saucedemo.com/cart.html",
        "flows.add_backpack_to_cart.cart_page.backpack_locator.value=[data-test='inventory-item-name']",
        "flows.add_backpack_to_cart.cart_page.quantity_locator.value=[data-test='item-quantity']",
        "flows.add_backpack_to_cart.cart_page.quantity_text=1",
    ]
    client = client_returning({
        "status": "generated", "filename": "test_backpack_flow.py",
        "test_name": "test_add_backpack_to_cart", "code": code,
        "grounded": True, "evidence_used": references,
        "missing_evidence": [],
    })

    result = GenerationAgent(map_path, client=client).generate(scenario())

    prompt = client.models.generate_content.call_args.kwargs["contents"]
    assert '"add_backpack_to_cart"' in prompt
    assert '"cart_href": null' in prompt
    assert result.status == "generated"
    assert result.grounded is True
    assert result.evidence_used == references


def test_requires_authenticated_map(tmp_path):
    map_path = tmp_path / "map.json"
    map_path.write_text('{"authenticated": false}', encoding="utf-8")

    with pytest.raises(ValueError, match="not authenticated"):
        GenerationAgent(map_path, client=MagicMock())


def test_selects_complete_multi_product_flow_and_excludes_single_flow(tmp_path):
    flow = {
        "products": [
            {"name": "Sauce Labs Backpack"},
            {"name": "Sauce Labs Bike Light"},
        ],
        "add_steps": [{"badge_value": "1"}, {"badge_value": "2"}],
    }
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({
        "authenticated": True,
        "products": [
            {"name": "Sauce Labs Backpack"},
            {"name": "Sauce Labs Bike Light"},
            {"name": "Sauce Labs Onesie"},
        ],
        "flows": {
            "add_backpack_and_bike_light_to_cart": flow,
            "add_other_pair_to_cart": {
                "products": [
                    {"name": "Sauce Labs Backpack"},
                    {"name": "Sauce Labs Onesie"},
                ]
            },
        },
    }), encoding="utf-8")
    client = client_returning({
        "status": "cannot_generate", "grounded": False,
        "missing_evidence": ["draft omitted for selection test"],
    })

    GenerationAgent(map_path, client=client).generate(multi_product_scenario())

    prompt = client.models.generate_content.call_args.kwargs["contents"]
    assert '"add_backpack_and_bike_light_to_cart"' in prompt
    assert '"add_other_pair_to_cart"' not in prompt


def test_unsupported_product_does_not_receive_multi_product_flow(tmp_path):
    unsupported = ScenarioModel(
        id="CART-003", title="Add Sauce Labs Backpack and Imaginary Hat to cart",
        description="Add both products", scenario_type="negative", priority="high",
        steps=["Add products"], expected_result="Both appear in cart",
    )
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps({
        "authenticated": True,
        "products": [
            {"name": "Sauce Labs Backpack"},
            {"name": "Sauce Labs Bike Light"},
        ],
        "flows": {"add_backpack_and_bike_light_to_cart": {
            "products": [
                {"name": "Sauce Labs Backpack"},
                {"name": "Sauce Labs Bike Light"},
            ]
        }},
    }), encoding="utf-8")
    client = client_returning({
        "status": "cannot_generate", "grounded": False,
        "missing_evidence": ["Imaginary Hat was not observed"],
    })

    result = GenerationAgent(map_path, client=client).generate(unsupported)

    prompt = client.models.generate_content.call_args.kwargs["contents"]
    assert '"add_backpack_and_bike_light_to_cart"' not in prompt
    assert result.status == "cannot_generate"
