import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import browser_mcp
import playwright_full
from browser_mcp import BrowserHandler, public_url


class BrowserHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_connect_attaches_to_9222_without_launching(self):
        browser = MagicMock()
        browser.is_connected.return_value = True
        driver = MagicMock()
        driver.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        driver.stop = AsyncMock()
        factory = MagicMock()
        factory.start = AsyncMock(return_value=driver)
        handler = BrowserHandler()
        with patch("browser_mcp.async_playwright", return_value=factory):
            self.assertTrue((await handler.connect())["connected"])
            await handler.connect()
        driver.chromium.connect_over_cdp.assert_awaited_once_with(
            "http://127.0.0.1:9222", timeout=15000
        )
        driver.chromium.launch.assert_not_called()
        await handler.disconnect()
        driver.stop.assert_awaited_once()
        browser.close.assert_not_called()

    async def test_connect_uses_active_port_when_http_discovery_unavailable(self):
        browser = MagicMock()
        browser.is_connected.return_value = True
        driver = MagicMock()
        driver.chromium.connect_over_cdp = AsyncMock(side_effect=[RuntimeError("404"), browser])
        driver.stop = AsyncMock()
        factory = MagicMock()
        factory.start = AsyncMock(return_value=driver)
        handler = BrowserHandler(devtools_active_port="DevToolsActivePort")
        with patch("browser_mcp.async_playwright", return_value=factory), patch(
            "browser_mcp.Path.read_text", return_value="9222\n/devtools/browser/test-browser\n"
        ):
            self.assertTrue((await handler.connect())["connected"])
        self.assertEqual(driver.chromium.connect_over_cdp.await_count, 2)
        driver.chromium.connect_over_cdp.assert_awaited_with(
            "ws://127.0.0.1:9222/devtools/browser/test-browser", timeout=15000
        )
        await handler.disconnect()

    def test_active_port_never_changes_configured_port_or_host(self):
        handler = BrowserHandler(devtools_active_port="DevToolsActivePort")
        for contents in ["9333\n/devtools/browser/test", "9222\nws://remote.example/test", "bad"]:
            with patch("browser_mcp.Path.read_text", return_value=contents):
                self.assertIsNone(handler.websocket_endpoint())

    async def test_failed_connection_cleans_up(self):
        driver = MagicMock()
        driver.chromium.connect_over_cdp = AsyncMock(side_effect=RuntimeError("failure"))
        driver.stop = AsyncMock()
        factory = MagicMock()
        factory.start = AsyncMock(return_value=driver)
        handler = BrowserHandler()
        with patch("browser_mcp.async_playwright", return_value=factory), patch.object(
            handler, "websocket_endpoint", return_value=None
        ):
            with self.assertRaisesRegex(RuntimeError, "Cannot attach"):
                await handler.connect()
        driver.stop.assert_awaited_once()
        self.assertFalse(handler.status()["connected"])

    async def test_tabs_have_target_ids_and_closed_tabs_are_rejected(self):
        handler = BrowserHandler()
        page = MagicMock()
        page.is_closed.return_value = False
        page.title = AsyncMock(return_value="Example")
        page.url = "https://example.com/path?code=private#token"
        session = MagicMock()
        session.send = AsyncMock(return_value={"targetInfo": {"targetId": "target-123"}})
        session.detach = AsyncMock()
        context = MagicMock()
        context.pages = [page]
        context.new_cdp_session = AsyncMock(return_value=session)
        handler.browser = MagicMock()
        handler.browser.contexts = [context]
        handler.connect = AsyncMock()
        self.assertEqual(await handler.list_tabs(), [{
            "tab_id": "target-123", "title": "Example", "url": "https://example.com/path"
        }])
        self.assertIs(await handler.page("target-123"), page)
        context.pages = []
        with self.assertRaisesRegex(ValueError, "Tab not found"):
            await handler.page("target-123")

    async def test_actions_disabled_before_browser_access(self):
        handler = BrowserHandler()
        handler.page = AsyncMock()
        with patch("browser_mcp.handler", handler):
            for action, arguments in [
                (browser_mcp.navigate, ("target", "https://example.com")),
                (browser_mcp.click, ("target", "button")),
                (browser_mcp.fill, ("target", "input", "text")),
                (browser_mcp.select_option, ("target", "select", "value")),
                (browser_mcp.press_key, ("target", "button", "Enter")),
            ]:
                with self.assertRaises(PermissionError):
                    await action(*arguments)
        handler.page.assert_not_awaited()

    async def test_password_fill_blocked(self):
        handler = BrowserHandler(allow_actions=True)
        page = MagicMock()
        locator = MagicMock()
        locator.get_attribute = AsyncMock(return_value="password")
        locator.fill = AsyncMock()
        page.locator.return_value = locator
        handler.page = AsyncMock(return_value=page)
        with patch("browser_mcp.handler", handler):
            with self.assertRaisesRegex(ValueError, "passwords directly"):
                await browser_mcp.fill("target", "input", "secret")
        locator.fill.assert_not_awaited()

    async def test_invalid_navigation_blocked(self):
        handler = BrowserHandler(allow_actions=True)
        handler.page = AsyncMock()
        with patch("browser_mcp.handler", handler):
            for url in ["javascript:alert(1)", "file:///etc/passwd", "https://user:secret@example.com"]:
                with self.assertRaises(ValueError):
                    await browser_mcp.navigate("target", url)
        handler.page.assert_not_awaited()

    async def test_inspection_bounds(self):
        with self.assertRaises(ValueError):
            await browser_mcp.inspect_page("target", max_chars=50001)

    async def test_tool_registration(self):
        tools = await browser_mcp.mcp.list_tools()
        self.assertEqual({tool.name for tool in tools}, {
            "connect_browser", "connection_status", "disconnect_browser", "list_tabs",
            "select_tab", "inspect_page", "screenshot", "navigate", "click", "fill",
            "select_option", "press_key",
        })
        inspect = next(tool for tool in tools if tool.name == "inspect_page")
        self.assertIn("tab_id", inspect.inputSchema["required"])

    def test_url_redaction(self):
        self.assertEqual(public_url("https://user:secret@example.com/a?code=123#token"), "https://example.com/a")


class FullPlaywrightLauncherTests(unittest.TestCase):
    def test_custom_profile_without_active_port_uses_http_discovery(self):
        with patch.dict(os.environ, {"BROWSER_MCP_USER_DATA_DIR": "custom-profile", "BROWSER_MCP_DEVTOOLS_ACTIVE_PORT": ""}), patch(
            "playwright_full.shutil.which", return_value="node"
        ), patch("playwright_full.Path.is_file", side_effect=[True, False]), patch.object(
            BrowserHandler, "websocket_endpoint", return_value=None
        ):
            args = playwright_full.command()
        self.assertIn("http://127.0.0.1:9222", args)

    def test_full_runtime_attaches_and_enables_capabilities(self):
        with patch("playwright_full.shutil.which", return_value="node"), patch(
            "playwright_full.Path.is_file", return_value=True
        ), patch.object(BrowserHandler, "websocket_endpoint", return_value="ws://127.0.0.1:9222/devtools/browser/test"):
            args = playwright_full.command()
        self.assertIn("--cdp-endpoint", args)
        self.assertIn("ws://127.0.0.1:9222/devtools/browser/test", args)
        self.assertIn("vision,pdf,devtools,testing,network,storage,config", args)
        self.assertNotIn("--user-data-dir", args)
        self.assertNotIn("--isolated", args)

    def test_custom_profile_must_publish_matching_endpoint(self):
        with patch.dict(os.environ, {"BROWSER_MCP_USER_DATA_DIR": "custom-profile", "BROWSER_MCP_DEVTOOLS_ACTIVE_PORT": ""}), patch(
            "playwright_full.shutil.which", return_value="node"
        ), patch("playwright_full.Path.is_file", return_value=True), patch.object(
            BrowserHandler, "websocket_endpoint", return_value=None
        ):
            with self.assertRaisesRegex(RuntimeError, "selected profile"):
                playwright_full.command()


@unittest.skipUnless(os.environ.get("BROWSER_MCP_LIVE_TEST") == "1", "Requires existing Chrome on 9222")
class LiveMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_connection_tabs_and_disconnect_preserves_chrome(self):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "browser_mcp"],
            cwd=str(Path(__file__).parent),
            env={**os.environ, "BROWSER_MCP_CDP_PORT": "9222", "BROWSER_MCP_ALLOW_ACTIONS": "0"},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = await client.list_tools()
                self.assertEqual(len(tools.tools), 12)
                connected = await client.call_tool("connect_browser", {})
                self.assertFalse(connected.isError)
                self.assertTrue(json.loads(connected.content[0].text)["connected"])

                async def current_tab_ids():
                    tabs = await client.call_tool("list_tabs", {})
                    self.assertFalse(tabs.isError)
                    decoded_tabs = []
                    for content in tabs.content:
                        decoded = json.loads(content.text)
                        decoded_tabs.extend(decoded if isinstance(decoded, list) else [decoded])
                    return {tab["tab_id"] for tab in decoded_tabs}

                before = await current_tab_ids()
                disconnected = await client.call_tool("disconnect_browser", {})
                self.assertFalse(disconnected.isError)
                self.assertFalse(json.loads(disconnected.content[0].text)["connected"])
                after = await current_tab_ids()
                self.assertEqual(before, after)
                await client.call_tool("disconnect_browser", {})


@unittest.skipUnless(os.environ.get("BROWSER_MCP_FULL_LIVE_TEST") == "1", "Requires Chrome and npm runtime")
class FullPlaywrightLiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_snapshots_and_screenshots_on_disposable_tab(self):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "playwright_full"],
            cwd=str(Path(__file__).parent),
            env={**os.environ, "BROWSER_MCP_CDP_PORT": "9222"},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = await client.list_tools()
                names = {tool.name for tool in tools.tools}
                self.assertTrue({
                    "browser_snapshot", "browser_take_screenshot", "browser_tabs",
                    "browser_click", "browser_fill_form", "browser_evaluate",
                    "browser_handle_dialog", "browser_file_upload", "browser_network_requests",
                    "browser_console_messages", "browser_pdf_save", "browser_verify_text_visible",
                    "browser_cookie_list", "browser_start_tracing",
                }.issubset(names))
                created = await client.call_tool("browser_tabs", {"action": "new"})
                self.assertFalse(created.isError)
                try:
                    result = await client.call_tool("browser_evaluate", {"function": """() => {
                        document.title = 'MCP disposable smoke test';
                        document.body.innerHTML = '<h1>MCP smoke test</h1><label>Name <input /></label><button>Continue</button>';
                        return true;
                    }"""})
                    self.assertFalse(result.isError)
                    snapshot = await client.call_tool("browser_snapshot", {})
                    self.assertFalse(snapshot.isError)
                    text = "\n".join(content.text for content in snapshot.content if content.type == "text")
                    self.assertIn("MCP smoke test", text)
                    self.assertIn("textbox", text)
                    self.assertIn("Continue", text)
                    screenshot = await client.call_tool("browser_take_screenshot", {"type": "png"})
                    self.assertFalse(screenshot.isError)
                    self.assertTrue(any(content.type == "image" for content in screenshot.content))
                finally:
                    closed = await client.call_tool("browser_tabs", {"action": "close"})
                    self.assertFalse(closed.isError)


if __name__ == "__main__":
    unittest.main()