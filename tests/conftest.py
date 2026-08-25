import json
import os
import re
from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright


class AuthenticationSetupError(RuntimeError):
    """The generated-test browser context cannot restore authentication."""


def _authenticated_storage_state() -> Path:
    configured = os.getenv("QA_STORAGE_STATE_PATH")
    path = Path(configured) if configured else (
        Path(__file__).resolve().parents[1] / "application_context" / "storage_state.json"
    )
    if not path.is_file():
        raise AuthenticationSetupError(
            f"Authentication setup error: storage state is missing: {path}"
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AuthenticationSetupError(
            f"Authentication setup error: storage state is invalid: {path}: {error}"
        ) from error
    if not isinstance(state, dict) or not isinstance(state.get("cookies"), list) \
            or not isinstance(state.get("origins"), list):
        raise AuthenticationSetupError(
            f"Authentication setup error: storage state is invalid: {path}"
        )
    return path.resolve()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, f"rep_{call.when}", outcome.get_result())


@pytest_asyncio.fixture
async def page(request):
    storage_state = _authenticated_storage_state()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=str(storage_state))
        page = await context.new_page()

        artifact_root = os.getenv("EXECUTION_ARTIFACT_DIR")
        browser_errors = []
        if artifact_root:
            page.on("console", lambda message: browser_errors.append(
                f"console.{message.type}: {message.text}"
            ) if message.type == "error" else None)
            page.on("pageerror", lambda error: browser_errors.append(f"pageerror: {error}"))
            await context.tracing.start(screenshots=True, snapshots=True, sources=True)

        yield page

        if artifact_root:
            artifact_dir = Path(artifact_root)
            slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid)
            failed = any(
                getattr(request.node, phase, None) is not None
                and getattr(request.node, phase).failed
                for phase in ("rep_setup", "rep_call")
            )
            try:
                if failed:
                    await page.screenshot(
                        path=artifact_dir / f"{slug}.png", full_page=True
                    )
                await context.tracing.stop(
                    path=artifact_dir / f"{slug}.zip" if failed else None
                )
            except Exception as error:
                browser_errors.append(f"evidence-capture-error: {error}")
            if browser_errors:
                (artifact_dir / f"{slug}-browser-errors.txt").write_text(
                    "\n".join(browser_errors), encoding="utf-8"
                )

        await context.close()
        await browser.close()
