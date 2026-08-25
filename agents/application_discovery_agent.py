import json
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright


class ApplicationDiscoveryAgent:

    LOCATOR_TIMEOUT = 2000

    def __init__(
        self,
        base_url: str,
        storage_state: str | None = None
    ):
        self.base_url = base_url
        self.storage_state = storage_state

    async def validate_page(self, page):
        title = await page.title()
        body_text = await page.locator("body").inner_text()

        if "Just a moment" in title:
            raise RuntimeError("Cloudflare challenge detected.")

        if not body_text.strip():
            raise RuntimeError("Application returned an empty page.")

        print("✓ Page validation passed")
        print(f"  Title: {title}")
        print(f"  URL: {page.url}")

    async def _collect_page_evidence(
        self,
        page,
        authenticated: bool
    ) -> dict[str, Any]:
        locator_timeout = 2000

        print("\nCollecting products...")
        products = []
        product_cards = page.locator(".inventory_item")
        product_count = await product_cards.count()

        print(f"\nProducts discovered: {product_count}")

        for index in range(product_count):
            card = product_cards.nth(index)
            product_link = card.locator(
                "a[href*='inventory-item.html']"
            )
            add_button = card.get_by_role(
                "button",
                name="Add to cart"
            )
            add_button_count = await add_button.count()

            href = None
            add_button_id = None
            add_button_data_test = None

            if await product_link.count() > 0:
                href = await product_link.first.get_attribute(
                    "href",
                    timeout=locator_timeout
                )

            if add_button_count > 0:
                add_button_id = await add_button.first.get_attribute(
                    "id",
                    timeout=locator_timeout
                )
                add_button_data_test = (
                    await add_button.first.get_attribute(
                        "data-test",
                        timeout=locator_timeout
                    )
                )

            locator_candidates = []

            if add_button_id:
                locator_candidates.append({
                    "strategy": "id",
                    "value": f"#{add_button_id}",
                    "confidence": 0.95
                })

            if add_button_data_test:
                locator_candidates.append({
                    "strategy": "data-test",
                    "value": f"[data-test='{add_button_data_test}']",
                    "confidence": 0.95
                })

            if add_button_count > 0:
                locator_candidates.append({
                    "strategy": "role",
                    "value": "button[name='Add to cart']",
                    "confidence": 0.90
                })

            name = card.locator(".inventory_item_name")
            price = card.locator(".inventory_item_price")
            description = card.locator(".inventory_item_desc")

            products.append({
                "name": (
                    await name.first.inner_text(timeout=locator_timeout)
                    if await name.count() > 0 else None
                ),
                "price": (
                    await price.first.inner_text(timeout=locator_timeout)
                    if await price.count() > 0 else None
                ),
                "description": (
                    await description.first.inner_text(
                        timeout=locator_timeout
                    )
                    if await description.count() > 0 else None
                ),
                "href": href,
                "add_to_cart": add_button_count > 0,
                "add_to_cart_id": add_button_id,
                "add_to_cart_data_test": add_button_data_test,
                "product_locator": (
                    await self._observed_locator(name)
                    if await name.count() > 0 else None
                ),
                "add_to_cart_locator": (
                    await self._observed_locator(add_button)
                    if add_button_count > 0 else None
                ),
                "locator_candidates": locator_candidates
            })

        print("Collecting cart...")
        cart_link = page.locator(".shopping_cart_link")
        cart_href = None

        if await cart_link.count() > 0:
            cart_href = await cart_link.first.get_attribute(
                "href",
                timeout=locator_timeout
            )

        cart_badge_visible = (
            await page.locator(".shopping_cart_badge").count() > 0
        )

        print("Collecting buttons...")
        buttons = []
        for button in await page.get_by_role("button").all():
            try:
                if await button.count() == 0:
                    continue
                buttons.append({
                    "text": (
                        await button.inner_text(timeout=locator_timeout)
                    ).strip(),
                    "aria_label": await button.get_attribute(
                        "aria-label", timeout=locator_timeout
                    ),
                    "id": await button.get_attribute(
                        "id", timeout=locator_timeout
                    ),
                    "class": await button.get_attribute(
                        "class", timeout=locator_timeout
                    )
                })
            except Exception:
                pass

        print("Collecting links...")
        links = []
        for link in await page.get_by_role("link").all():
            try:
                if await link.count() == 0:
                    continue
                links.append({
                    "text": (
                        await link.inner_text(timeout=locator_timeout)
                    ).strip(),
                    "href": await link.get_attribute(
                        "href", timeout=locator_timeout
                    ),
                    "class": await link.get_attribute(
                        "class", timeout=locator_timeout
                    )
                })
            except Exception:
                pass

        print("Collecting inputs...")
        inputs = []
        for input_element in await page.locator("input").all():
            try:
                if await input_element.count() == 0:
                    continue
                inputs.append({
                    "type": await input_element.get_attribute(
                        "type", timeout=locator_timeout
                    ),
                    "name": await input_element.get_attribute(
                        "name", timeout=locator_timeout
                    ),
                    "placeholder": await input_element.get_attribute(
                        "placeholder", timeout=locator_timeout
                    ),
                    "id": await input_element.get_attribute(
                        "id", timeout=locator_timeout
                    )
                })
            except Exception:
                pass

        print("Collecting ARIA snapshot...")
        try:
            body = page.locator("body")
            aria_snapshot = (
                await body.first.aria_snapshot(
                    mode="ai",
                    timeout=locator_timeout
                )
                if await body.count() > 0 else None
            )
        except Exception:
            aria_snapshot = None

        print("Collecting network/API evidence...")
        network_api_evidence = await page.evaluate(
            """() => performance.getEntriesByType('resource')
                .filter(entry => ['fetch', 'xmlhttprequest'].includes(
                    entry.initiatorType
                ))
                .map(entry => ({
                    url: entry.name,
                    initiator_type: entry.initiatorType
                }))"""
        )

        return {
            "application": "SauceDemo",
            "base_url": self.base_url,
            "authenticated": authenticated,
            "page": {
                "url": page.url,
                "title": await page.title()
            },
            "products": products,
            "cart": {
                "href": cart_href,
                "badge_present": cart_badge_visible
            },
            "buttons": buttons,
            "links": links,
            "inputs": inputs,
            "aria_snapshot": aria_snapshot,
            "network_api_evidence": network_api_evidence
        }

    async def _observed_locator(self, locator) -> dict[str, str] | None:
        """Build a locator only from attributes observed on the element."""
        if await locator.count() == 0:
            return None

        element = locator.first
        for attribute, strategy in (
            ("data-test", "data-test"),
            ("id", "id"),
            ("aria-label", "aria-label"),
        ):
            value = await element.get_attribute(
                attribute,
                timeout=self.LOCATOR_TIMEOUT
            )
            if value:
                prefix = "#" if attribute == "id" else ""
                selector = (
                    f"{prefix}{value}"
                    if attribute == "id"
                    else f"[{attribute}='{value}']"
                )
                return {"strategy": strategy, "value": selector}

        href = await element.get_attribute(
            "href", timeout=self.LOCATOR_TIMEOUT
        )
        if href:
            return {"strategy": "href", "value": f"a[href='{href}']"}

        classes = await element.get_attribute(
            "class", timeout=self.LOCATOR_TIMEOUT
        )
        if classes:
            class_selector = "." + ".".join(classes.split())
            return {"strategy": "class", "value": class_selector}

        return None

    async def _discover_cart_flow(
        self, page, product_names: list[str]
    ) -> dict[str, Any]:
        """Exercise a reusable ordered, multi-product cart flow.

        Every value returned here is read from the live UI.  The product list is
        the only input, so additional grounded combinations do not require new
        test-generation code or a new discovery algorithm.
        """
        timeout = self.LOCATOR_TIMEOUT
        start_url = page.url
        cleanup = {"cart_empty": False, "badge_present": None}
        product_cards = page.locator(".inventory_item")
        observed_products = {}
        for index in range(await product_cards.count()):
            card = product_cards.nth(index)
            name = card.locator(".inventory_item_name")
            if await name.count() == 0:
                continue
            observed_name = (
                await name.first.inner_text(timeout=timeout)
            ).strip()
            if observed_name in product_names:
                observed_products[observed_name] = (card, name.first)
        missing = [name for name in product_names if name not in observed_products]
        if missing:
            raise RuntimeError(f"Products were not observed: {', '.join(missing)}")

        products = []
        for product_name in product_names:
            card, name = observed_products[product_name]
            initial_remove = card.get_by_role("button", name="Remove")
            if await initial_remove.count() > 0:
                await initial_remove.first.click(timeout=timeout)
            add_button = card.get_by_role("button", name="Add to cart")
            if await add_button.count() == 0:
                raise RuntimeError(f"{product_name} has no Add to cart control.")
            product_locator = await self._observed_locator(name)
            add_locator = await self._observed_locator(add_button)
            if product_locator is None or add_locator is None:
                raise RuntimeError(f"Could not derive locators for {product_name}.")
            products.append({
                "name": product_name,
                "product_locator": product_locator,
                "add_to_cart_locator": add_locator,
            })
        flow: dict[str, Any] = {
            "preconditions": {
                "authenticated": True,
                "inventory_url": start_url,
                "cart_empty": True
            },
            "products": products,
            "add_steps": [],
        }
        try:
            for expected_badge, product in enumerate(products, start=1):
                card, _ = observed_products[product["name"]]
                await card.get_by_role(
                    "button", name="Add to cart"
                ).first.click(timeout=timeout)
                badge = page.locator(".shopping_cart_badge")
                if await badge.count() == 0:
                    raise RuntimeError("Shopping cart badge did not appear.")
                badge_text = (await badge.first.inner_text(timeout=timeout)).strip()
                if badge_text != str(expected_badge):
                    raise RuntimeError(
                        f"Expected badge {expected_badge}, observed {badge_text}."
                    )
                flow["add_steps"].append({
                    "product_name": product["name"],
                    "add_to_cart_locator": product["add_to_cart_locator"],
                    "shopping_cart_badge_locator": await self._observed_locator(badge),
                    "badge_value": badge_text,
                })

            cart_link = page.locator(".shopping_cart_link")
            if await cart_link.count() == 0:
                raise RuntimeError("Shopping cart link was not observed.")
            flow["cart_navigation"] = {
                "shopping_cart_link_locator": await self._observed_locator(cart_link),
                "cart_href": await cart_link.first.get_attribute("href", timeout=timeout),
            }
            await cart_link.first.click(timeout=timeout)
            await page.locator("body").wait_for(state="visible", timeout=timeout)
            cart_items = page.locator(".cart_item")
            cart_evidence = []
            for index in range(await cart_items.count()):
                item = cart_items.nth(index)
                name = item.locator(".inventory_item_name")
                if await name.count() == 0:
                    continue
                observed_name = (
                    await name.first.inner_text(timeout=timeout)
                ).strip()
                if observed_name not in product_names:
                    continue
                quantity = item.locator(".cart_quantity")
                if await quantity.count() == 0:
                    raise RuntimeError(f"Quantity not observed for {observed_name}.")
                quantity_text = (await quantity.first.inner_text(timeout=timeout)).strip()
                if quantity_text != "1":
                    raise RuntimeError(f"Expected quantity 1 for {observed_name}.")
                cart_evidence.append({
                    "name": observed_name,
                    "product_locator": await self._observed_locator(name),
                    "quantity_locator": await self._observed_locator(quantity),
                    "quantity": quantity_text,
                })
            if {item["name"] for item in cart_evidence} != set(product_names):
                raise RuntimeError("Not all requested products were found in cart.")
            flow["cart_page"] = {
                "actual_url": page.url,
                "items": cart_evidence,
            }
        finally:
            # Remove every item introduced by the flow, even after partial failure.
            await page.goto(
                self.base_url.rstrip("/") + "/inventory.html",
                wait_until="domcontentloaded", timeout=5000
            )
            cards = page.locator(".inventory_item")
            for index in range(await cards.count()):
                card = cards.nth(index)
                name = card.locator(".inventory_item_name")
                if await name.count() == 0:
                    continue
                observed_name = (await name.first.inner_text(timeout=timeout)).strip()
                if observed_name in product_names:
                    remove = card.get_by_role("button", name="Remove")
                    if await remove.count() > 0:
                        await remove.first.click(timeout=timeout)
            badge = page.locator(".shopping_cart_badge")
            cleanup["badge_present"] = await badge.count() > 0
            cleanup["cart_empty"] = not cleanup["badge_present"]
            flow["cleanup"] = cleanup
            if not cleanup["cart_empty"]:
                raise RuntimeError("Cart cleanup failed; cart is not empty.")
        return flow

    async def _discover_add_backpack_to_cart(self, page) -> dict[str, Any]:
        return await self._discover_cart_flow(page, ["Sauce Labs Backpack"])

    async def discover_authenticated(self):
        """Discover the inventory using the previously authenticated state.

        This flow intentionally creates a context from ``storage_state``
        directly.  Calling :meth:`discover` here would create a fresh,
        unauthenticated context and lose the login session.
        """
        if not self.storage_state:
            raise ValueError(
                "storage_state is required "
                "for authenticated discovery."
            )

        storage_path = Path(self.storage_state).resolve()

        if not storage_path.exists():
            raise FileNotFoundError(
                f"Storage state not found: {storage_path}"
            )

        print(f"\nLoading storage state:\n{storage_path}")

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)

            try:
                context = await browser.new_context(
                    storage_state=str(storage_path)
                )
                page = await context.new_page()
                target_url = (
                    self.base_url.rstrip("/")
                    + "/inventory.html"
                )

                print(f"\nOpening authenticated page:\n{target_url}")

                await page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )
                await page.locator("body").wait_for(
                    state="visible",
                    timeout=30000
                )
                await self.validate_page(page)

                if "/inventory.html" not in page.url:
                    raise RuntimeError(
                        "Authenticated discovery failed. "
                        "The saved session did not reach the "
                        "authenticated inventory page. "
                        f"Actual URL: {page.url}"
                    )

                inventory = page.locator(".inventory_list")
                if await inventory.count() == 0:
                    raise RuntimeError(
                        "Authenticated session is invalid. "
                        "Inventory page was not found."
                    )

                print("✓ Authenticated inventory page verified")

                discovery = await self._collect_page_evidence(
                    page,
                    authenticated=True
                )
                discovery["flows"] = {
                    "add_backpack_to_cart": (
                        await self._discover_add_backpack_to_cart(page)
                    ),
                    "add_backpack_and_bike_light_to_cart": (
                        await self._discover_cart_flow(page, [
                            "Sauce Labs Backpack",
                            "Sauce Labs Bike Light",
                        ])
                    )
                }
                return discovery
            finally:
                await browser.close()

    async def discover(self):
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)

            try:
                context = await browser.new_context()
                page = await context.new_page()
                target_url = self.base_url.rstrip("/") + "/"

                print(f"\nOpening page:\n{target_url}")

                await page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )
                await page.locator("body").wait_for(
                    state="visible",
                    timeout=30000
                )
                await self.validate_page(page)

                return await self._collect_page_evidence(
                    page,
                    authenticated=False
                )
            finally:
                await browser.close()

    def save_authenticated(
        self,
        discovery: dict[str, Any]
    ):
        output_directory = Path("application_context")
        output_directory.mkdir(parents=True, exist_ok=True)
        output_file = (
            output_directory
            / "authenticated_application_map.json"
        )
        output_file.write_text(
            json.dumps(discovery, indent=2),
            encoding="utf-8"
        )

        print(
            f"\n✓ Authenticated application map saved:"
            f"\n{output_file}"
        )

    def save(self, discovery: dict[str, Any]):
        output_directory = Path("application_context")
        output_directory.mkdir(parents=True, exist_ok=True)
        output_file = output_directory / "application_map.json"
        output_file.write_text(
            json.dumps(discovery, indent=2),
            encoding="utf-8"
        )

        print(f"\n✓ Application map saved:\n{output_file}")
