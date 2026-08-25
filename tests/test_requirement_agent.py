import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from agents.requirement_agent import RequirementAgent


def test_prompt_requires_strict_acceptance_criteria_grounding():
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text=json.dumps({
        "feature": "Cart",
        "summary": "Add the Backpack to the cart",
        "scenarios": [{
            "id": "CART-001",
            "title": "Add Sauce Labs Backpack to cart",
            "description": "Verify the stated authenticated cart flow",
            "scenario_type": "positive",
            "priority": "high",
            "steps": [
                "Open the authenticated Products page",
                "Verify Sauce Labs Backpack is visible",
                "Add Sauce Labs Backpack to the cart",
                "Verify the cart badge is 1",
                "Open the cart",
                "Verify Sauce Labs Backpack is present with quantity 1",
            ],
            "expected_result": "Sauce Labs Backpack is in the cart with quantity 1",
        }],
    }))
    requirement = """Authenticated Products page. Sauce Labs Backpack is visible.
    Add it to the cart, verify badge 1, open cart, and verify Backpack quantity 1."""

    result = RequirementAgent(client=client).analyze(requirement)

    prompt = client.models.generate_content.call_args.kwargs["contents"]
    assert "acceptance criteria as authoritative" in prompt
    assert "Do NOT invent additional business flows" in prompt
    assert "product-detail, remove-item, unauthorized-access" in prompt
    assert "negative or edge scenarios only when they are directly implied" in prompt
    assert "Prefer fewer precise scenarios" in prompt
    assert requirement in prompt
    assert len(result.scenarios) == 1
    assert result.scenarios[0].steps[-1] == (
        "Verify Sauce Labs Backpack is present with quantity 1"
    )
