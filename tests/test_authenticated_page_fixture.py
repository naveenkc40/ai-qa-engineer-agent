import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import conftest


class FakePage:
    def __init__(self):
        self.url = "about:blank"

    async def goto(self, url):
        self.url = url

    def on(self, *_args):
        pass


class FakeContext:
    def __init__(self):
        self.page = FakePage()
        self.closed = False

    async def new_page(self):
        return self.page

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.context = FakeContext()
        self.storage_state = None
        self.closed = False

    async def new_context(self, **kwargs):
        self.storage_state = kwargs.get("storage_state")
        return self.context

    async def close(self):
        self.closed = True


def valid_state(path):
    path.write_text(json.dumps({"cookies": [], "origins": []}), encoding="utf-8")


def fake_playwright(browser):
    @asynccontextmanager
    async def manager():
        chromium = SimpleNamespace(launch=lambda **_kwargs: async_value(browser))
        yield SimpleNamespace(chromium=chromium)
    return manager


async def async_value(value):
    return value


def request():
    return SimpleNamespace(node=SimpleNamespace(nodeid="generated::test", rep_setup=None, rep_call=None))


@pytest.mark.asyncio
async def test_authenticated_context_loads_inventory(tmp_path, monkeypatch):
    state = tmp_path / "storage_state.json"
    valid_state(state)
    browser = FakeBrowser()
    monkeypatch.setenv("QA_STORAGE_STATE_PATH", str(state))
    monkeypatch.setattr(conftest, "async_playwright", fake_playwright(browser))

    fixture = conftest.page.__wrapped__(request())
    page = await anext(fixture)
    await page.goto("https://www.saucedemo.com/inventory.html")

    assert page.url.endswith("/inventory.html")
    assert browser.storage_state == str(state.resolve())
    await fixture.aclose()


def test_missing_storage_state_is_authentication_setup_error(tmp_path, monkeypatch):
    monkeypatch.setenv("QA_STORAGE_STATE_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(conftest.AuthenticationSetupError, match="storage state is missing"):
        conftest._authenticated_storage_state()


def test_invalid_storage_state_is_authentication_setup_error(tmp_path, monkeypatch):
    state = tmp_path / "storage_state.json"
    state.write_text("not json", encoding="utf-8")
    monkeypatch.setenv("QA_STORAGE_STATE_PATH", str(state))
    with pytest.raises(conftest.AuthenticationSetupError, match="storage state is invalid"):
        conftest._authenticated_storage_state()


@pytest.mark.asyncio
async def test_generated_test_uses_authenticated_page_fixture(tmp_path, monkeypatch):
    state = tmp_path / "storage_state.json"
    valid_state(state)
    browser = FakeBrowser()
    monkeypatch.setenv("QA_STORAGE_STATE_PATH", str(state))
    monkeypatch.setattr(conftest, "async_playwright", fake_playwright(browser))

    async def generated_test(page):
        await page.goto("https://www.saucedemo.com/inventory.html")
        assert page.url.endswith("/inventory.html")

    fixture = conftest.page.__wrapped__(request())
    authenticated_page = await anext(fixture)
    await generated_test(authenticated_page)

    assert browser.storage_state == str(state.resolve())
    await fixture.aclose()
