import json
import os
import re
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field

from agents.gemini_retry import call_gemini_with_retry

load_dotenv()


class GeneratedTest(BaseModel):
    status: Literal["generated", "cannot_generate"] = "generated"
    filename: str = ""
    test_name: str = ""
    code: str = ""
    grounded: bool = False
    evidence_used: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class TestGenerationAgent:
    DEFAULT_MAP_PATH = Path("application_context/authenticated_application_map.json")

    def __init__(self, application_map_path=None, client=None):
        self.application_map_path = Path(application_map_path or self.DEFAULT_MAP_PATH)
        self.application_map = self._load_application_map()
        if client is not None:
            self.client = client
            return
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not configured in .env")
        self.client = genai.Client(api_key=api_key)

    def _load_application_map(self) -> dict:
        if not self.application_map_path.is_file():
            raise FileNotFoundError(
                f"Authenticated application map not found: {self.application_map_path}"
            )
        try:
            application_map = json.loads(
                self.application_map_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as error:
            raise ValueError("Authenticated application map is invalid JSON") from error
        if not application_map.get("authenticated"):
            raise ValueError("Application map is not authenticated")
        return application_map

    def _relevant_evidence(self, scenario) -> dict:
        searchable = " ".join(
            [scenario.title, scenario.description, *scenario.steps,
             scenario.expected_result]
        ).lower()
        products = self.application_map.get("products", [])
        matched_products = [
            product for product in products
            if product.get("name", "").lower() in searchable
        ]
        if not matched_products and any(
            word in searchable for word in ("product", "cart", "inventory")
        ):
            matched_products = products
        flows = self.application_map.get("flows", {})
        requested_product_names = {
            product.get("name") for product in products
            if product.get("name")
            and product["name"].lower() in searchable
        }
        def flow_product_names(flow):
            names = []
            for product in flow.get("products", []):
                if isinstance(product, dict) and product.get("name"):
                    names.append(product["name"])
            legacy_name = flow.get("preconditions", {}).get("product_name")
            if legacy_name:
                names.append(legacy_name)
            return names

        matched_flows = {}
        for name, flow in flows.items():
            product_names = flow_product_names(flow)
            # A stateful flow is eligible only when every product it exercises
            # is explicitly requested. This prevents one-product requirements
            # from inheriting unsupported multi-product states (and vice versa).
            if (
                product_names
                and set(product_names) == requested_product_names
                and "cart" in searchable
            ):
                matched_flows[name] = flow
        if matched_flows:
            largest_product_count = max(
                len(flow_product_names(flow))
                for flow in matched_flows.values()
            )
            matched_flows = {
                name: flow for name, flow in matched_flows.items()
                if len(flow_product_names(flow)) == largest_product_count
            }
        return {
            "application": self.application_map.get("application"),
            "base_url": self.application_map.get("base_url"),
            "page": self.application_map.get("page", {}),
            "products": matched_products,
            "cart": self.application_map.get("cart", {}),
            "buttons": self.application_map.get("buttons", []),
            "links": self.application_map.get("links", []),
            "inputs": self.application_map.get("inputs", []),
            "aria_snapshot": self.application_map.get("aria_snapshot", ""),
            "network_api_evidence": self.application_map.get("network_api_evidence", []),
            "flows": matched_flows,
        }

    @staticmethod
    def _evidence_catalog(value, path="") -> set[str]:
        catalog = set()
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                catalog.update(TestGenerationAgent._evidence_catalog(child, child_path))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                catalog.update(TestGenerationAgent._evidence_catalog(child, f"{path}[{index}]"))
        else:
            catalog.add(f"{path}={value}")
        return catalog

    def _unsupported_literals(self, code: str, evidence: dict) -> list[str]:
        missing = []
        urls = {
            value for value in (
                evidence.get("base_url"), evidence.get("page", {}).get("url")
            ) if value
        }
        urls.update(
            link["href"] for link in evidence.get("links", [])
            if link.get("href") and link["href"] != "#"
        )
        # Stateful discovery records navigation destinations where they were
        # actually observed. Only URL-shaped fields are admitted here.
        def observed_urls(value):
            found = set()
            if isinstance(value, dict):
                for key, child in value.items():
                    if isinstance(child, str) and (
                        key == "url" or key.endswith("_url") or key == "href"
                    ):
                        found.add(child)
                    else:
                        found.update(observed_urls(child))
            elif isinstance(value, list):
                for child in value:
                    found.update(observed_urls(child))
            return found

        urls.update(observed_urls(evidence.get("flows", {})))
        for _, url in re.findall(r"\.goto\(\s*(['\"])(.*?)\1", code):
            if url not in urls:
                missing.append(f"URL not in application map: {url}")
        for _, url in re.findall(r"\.to_have_url\(\s*(['\"])(.*?)\1", code):
            if url not in urls:
                missing.append(f"URL not in application map: {url}")

        allowed_selectors = set()
        allowed_test_ids = set()

        def observed_locators(value):
            if isinstance(value, dict):
                if (
                    isinstance(value.get("strategy"), str)
                    and isinstance(value.get("value"), str)
                ):
                    selector = value["value"]
                    allowed_selectors.add(selector)
                    if value["strategy"] == "data-test":
                        match = re.fullmatch(
                            r"\[data-test=(?:'|\")(.+?)(?:'|\")\]", selector
                        )
                        if match:
                            allowed_test_ids.add(match.group(1))
                for child in value.values():
                    observed_locators(child)
            elif isinstance(value, list):
                for child in value:
                    observed_locators(child)

        observed_locators(evidence.get("flows", {}))
        for product in evidence.get("products", []):
            if product.get("add_to_cart_id"):
                allowed_selectors.add(f"#{product['add_to_cart_id']}")
            if product.get("add_to_cart_data_test"):
                test_id = product["add_to_cart_data_test"]
                allowed_test_ids.add(test_id)
                allowed_selectors.add(f"[data-test='{test_id}']")
            allowed_selectors.update(
                item.get("value") for item in product.get("locator_candidates", [])
                if item.get("value")
            )
        allowed_selectors.update(
            f"#{button['id']}" for button in evidence.get("buttons", [])
            if button.get("id")
        )
        for _, selector in re.findall(r"\.locator\(\s*(['\"])(.*?)\1", code):
            if selector not in allowed_selectors:
                missing.append(f"selector not in application map: {selector}")
        for _, test_id in re.findall(r"\.get_by_test_id\(\s*(['\"])(.*?)\1", code):
            if test_id not in allowed_test_ids:
                missing.append(f"test id not in application map: {test_id}")

        allowed_roles = {
            ("button", button.get("aria_label") or button.get("text"))
            for button in evidence.get("buttons", [])
        }
        allowed_roles.update(
            ("link", link.get("text")) for link in evidence.get("links", [])
            if link.get("text")
        )
        allowed_roles.update(
            re.findall(r'- ([a-z]+) "([^"]+)"', evidence.get("aria_snapshot", ""))
        )
        role_calls = re.findall(
            r"\.get_by_role\(\s*['\"]([^'\"]+)['\"]\s*,\s*name\s*=\s*['\"]([^'\"]+)['\"]",
            code,
        )
        for role_call in role_calls:
            if role_call not in allowed_roles:
                missing.append(
                    f"role/name not in application map: {role_call[0]}/{role_call[1]}"
                )

        allowed_labels = {
            value for item in evidence.get("inputs", [])
            for value in (item.get("label"), item.get("aria_label")) if value
        }
        for _, label in re.findall(r"\.get_by_label\(\s*(['\"])(.*?)\1", code):
            if label not in allowed_labels:
                missing.append(f"label not in application map: {label}")
        return missing

    def _grounding_check(self, generated: GeneratedTest, evidence: dict) -> GeneratedTest:
        if generated.status == "cannot_generate":
            generated.grounded = False
            generated.code = ""
            generated.filename = ""
            return generated
        catalog = self._evidence_catalog(evidence)
        problems = self._unsupported_literals(generated.code, evidence)
        problems.extend(
            f"unknown evidence reference: {reference}"
            for reference in generated.evidence_used if reference not in catalog
        )
        if not generated.evidence_used:
            problems.append("no evidence references supplied")
        if not generated.filename or not generated.code or not generated.test_name:
            problems.append("generated result is missing filename, test_name, or code")
        if generated.filename and (
            Path(generated.filename).name != generated.filename
            or not generated.filename.endswith(".py")
        ):
            problems.append("filename must be a Python basename under tests/generated")
        if problems:
            return GeneratedTest(
                status="cannot_generate",
                test_name=generated.test_name,
                grounded=False,
                evidence_used=[ref for ref in generated.evidence_used if ref in catalog],
                missing_evidence=problems,
            )
        generated.grounded = True
        generated.missing_evidence = []
        return generated

    def generate(self, scenario, application_url: str | None = None) -> GeneratedTest:
        evidence = self._relevant_evidence(scenario)
        catalog = sorted(self._evidence_catalog(evidence))
        prompt = f"""
You are a senior Playwright Python automation engineer. Generate an async
Playwright pytest test ONLY when every UI fact is directly supported below.

SCENARIO:
{scenario.model_dump_json(indent=2)}

AUTHENTICATED_APPLICATION_EVIDENCE:
{json.dumps(evidence, indent=2)}

VALID EVIDENCE REFERENCES (copy exact strings into evidence_used):
{json.dumps(catalog, indent=2)}

Rules:
1. Never invent or infer URLs, routes, selectors, test IDs, data attributes,
   products, cart states, buttons, fields, labels, ARIA names, or UI results.
2. Ignore caller application_url; navigate only to an exact evidenced URL.
3. Locator priority: get_by_role, get_by_label, get_by_test_id/data-test,
   stable id, stable CSS. Skip a higher choice when it is ambiguous.
4. Use Playwright Python, pytest, async tests, assertions, and no arbitrary waits.
5. A generated filename is a basename saved under tests/generated. Do not run it.
6. For supported scenarios return status="generated", grounded=true, exact
   evidence references from the list, and no missing_evidence.
7. If any step or expected result lacks evidence, return status="cannot_generate",
   grounded=false, empty filename/code/evidence_used, and explain missing_evidence.
8. Stateful flow evidence is direct observation. Cite the exact flows.* catalog
   references used for every navigation, locator, action, and asserted state.
9. A null cart_href is not missing evidence when the flow observes the cart link
   locator, navigation by clicking that link, and the resulting cart actual_url.
   Click the observed link; do not invent or infer an href.
"""
        response = call_gemini_with_retry(
            lambda: self.client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
                config={"response_mime_type": "application/json", "response_schema": GeneratedTest},
            )
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        return self._grounding_check(
            GeneratedTest.model_validate_json(response.text), evidence
        )
