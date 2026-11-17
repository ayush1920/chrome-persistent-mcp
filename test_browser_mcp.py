import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ModuleNotFoundError:
    ClientSession = None  # type: ignore[misc,assignment]
    StdioServerParameters = None  # type: ignore[misc,assignment]
    stdio_client = None  # type: ignore[misc,assignment]

import browser_mcp
from browser_mcp import AGENT_INSTRUCTIONS, BrowserHandler, public_url


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
        with patch("browser_mcp.async_playwright", return_value=factory), patch.object(
            handler, "websocket_endpoint", return_value=None
        ):
            first = await handler.connect()
            self.assertTrue(first["connected"])
            self.assertFalse(first["reused_existing_websocket"])
            self.assertEqual(first["handshake_count"], 1)
            second = await handler.connect()
            self.assertTrue(second["reused_existing_websocket"])
            self.assertEqual(second["handshake_count"], 1)
        driver.chromium.connect_over_cdp.assert_awaited_once_with(
            "http://127.0.0.1:9222", timeout=15000
        )
        driver.chromium.launch.assert_not_called()
        await handler.disconnect()
        driver.stop.assert_awaited_once()
        browser.close.assert_not_called()

    async def test_connect_prefers_persistent_websocket_when_available(self):
        browser = MagicMock()
        browser.is_connected.return_value = True
        driver = MagicMock()
        driver.chromium.connect_over_cdp = AsyncMock(return_value=browser)
        driver.stop = AsyncMock()
        factory = MagicMock()
        factory.start = AsyncMock(return_value=driver)
        handler = BrowserHandler()
        ws_url = "ws://127.0.0.1:9222/devtools/browser/persistent-123"
        with patch("browser_mcp.async_playwright", return_value=factory), patch.object(
            handler, "websocket_endpoint", return_value=ws_url
        ):
            status = await handler.connect(prefer_websocket=True)
            self.assertTrue(status["connected"])
            self.assertEqual(status["ws_endpoint"], ws_url)
            self.assertEqual(status["transport"], "websocket")
        driver.chromium.connect_over_cdp.assert_awaited_once_with(ws_url, timeout=15000)
        await handler.disconnect()

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

    async def test_tabs_cache_target_ids_without_repeated_cdp_probing(self):
        handler = BrowserHandler()
        page = MagicMock()
        page.is_closed.return_value = False
        page.title = AsyncMock(return_value="Example")
        page.url = "https://example.com/path?code=private#token"
        page.on = MagicMock()
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
        # Subsequent list_tabs() and page() calls reuse cached targetId and never open extra CDP sessions
        await handler.list_tabs()
        self.assertIs(await handler.page("target-123"), page)
        context.new_cdp_session.assert_awaited_once()
        self.assertTrue(handler.get_telemetry("target-123").attached)
        page.is_closed.return_value = True
        context.pages = []
        with self.assertRaisesRegex(ValueError, "Tab not found"):
            await handler.page("target-123")

    async def test_disconnect_browser_keeps_websocket_alive_by_default_when_configured(self):
        handler = BrowserHandler()
        handler.browser = MagicMock()
        handler.browser.is_connected.return_value = True
        handler.active_ws_endpoint = "ws://127.0.0.1:9222/devtools/browser/persistent-123"
        handler.disconnect = AsyncMock(return_value={"connected": False})
        with patch("browser_mcp.handler", handler), patch.dict(
            os.environ, {"BROWSER_MCP_KEEP_WEBSOCKET_ALIVE": "1"}
        ):
            kept = await browser_mcp.disconnect_browser(force=False)
            self.assertTrue(kept["connected"])
            self.assertTrue(kept["kept_alive"])
            handler.disconnect.assert_not_awaited()

            forced = await browser_mcp.disconnect_browser(force=True)
            self.assertFalse(forced["connected"])
            handler.disconnect.assert_awaited_once()

    async def test_console_and_network_telemetry_tools(self):
        handler = BrowserHandler(allow_actions=True)
        page = MagicMock()
        handler.page = AsyncMock(return_value=page)
        telemetry = handler.get_telemetry("target-1")
        telemetry.record_console("error", "Uncaught ReferenceError: foo is not defined", "app.js:42")
        telemetry.record_network_request("req-1", "POST", "https://api.example.com/v1/items?secret=1", "fetch")
        telemetry.record_ws_frame("received", "ws://127.0.0.1:9222/realtime", '{"type":"ping"}')

        with patch("browser_mcp.handler", handler):
            logs = await browser_mcp.get_console_logs("target-1", level="error")
            self.assertEqual(logs["count"], 1)
            self.assertIn("ReferenceError", logs["logs"][0]["text"])

            reqs = await browser_mcp.get_network_requests("target-1", resource_type="fetch")
            self.assertEqual(reqs["count"], 1)
            self.assertEqual(reqs["requests"][0]["url"], "https://api.example.com/v1/items")

            frames = await browser_mcp.get_websocket_frames("target-1")
            self.assertEqual(frames["count"], 1)
            self.assertEqual(frames["frames"][0]["direction"], "received")

    async def test_dom_manipulation_and_cdp_tools(self):
        handler = BrowserHandler(allow_actions=True)
        page = MagicMock()
        page.evaluate = AsyncMock(return_value={"found": True, "tag": "div", "operation": "set_text"})
        handler.page = AsyncMock(return_value=page)
        cdp = MagicMock()
        cdp.send = AsyncMock(return_value={"root": {"nodeId": 1}})
        handler.cdp_session = AsyncMock(return_value=cdp)

        with patch("browser_mcp.handler", handler):
            dom_res = await browser_mcp.modify_dom("target-1", "#banner", "set_text", value="Updated")
            self.assertTrue(dom_res["found"])
            cdp_res = await browser_mcp.cdp_send("target-1", "DOM.getDocument", {"depth": 1})
            self.assertEqual(cdp_res["result"]["root"]["nodeId"], 1)

    async def test_actions_disabled_before_browser_access(self):
        handler = BrowserHandler(allow_actions=False)
        handler.page = AsyncMock()
        with patch("browser_mcp.handler", handler):
            for action, arguments in [
                (browser_mcp.navigate, ("target", "https://example.com")),
                (browser_mcp.click, ("target", "button")),
                (browser_mcp.fill, ("target", "input", "text")),
                (browser_mcp.select_option, ("target", "select", "value")),
                (browser_mcp.press_key, ("target", "button", "Enter")),
                (browser_mcp.modify_dom, ("target", "#el", "set_text", "hi")),
                (browser_mcp.evaluate_js, ("target", "() => 1")),
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

    async def test_tool_registration_and_agent_instructions(self):
        self.assertIn("SINGLE PERSISTENT WEBSOCKET CONNECTION", AGENT_INSTRUCTIONS)
        self.assertIn("DO NOT PROBE PORT 9222 FROM THE TERMINAL", AGENT_INSTRUCTIONS)
        tools = await browser_mcp.mcp.list_tools()
        tool_names = {tool.name for tool in tools}
        expected_core = {
            "connect_browser", "connect_websocket", "connection_status", "disconnect_browser",
            "list_tabs", "select_tab", "manage_tabs", "inspect_page", "accessibility_snapshot",
            "screenshot", "get_console_logs", "clear_console_logs", "get_network_requests",
            "get_network_response_body", "clear_network_requests", "get_websocket_frames",
            "route_network", "query_selector_all", "modify_dom", "get_computed_styles",
            "evaluate_js", "navigate", "click", "fill", "select_option", "press_key",
            "hover", "drag_and_drop", "wait_for_selector", "handle_dialog", "upload_file",
            "get_storage_state", "set_storage_item", "save_pdf", "start_tracing",
            "stop_tracing", "cdp_send",
        }
        self.assertTrue(expected_core.issubset(tool_names))
        inspect = next(tool for tool in tools if tool.name == "inspect_page")
        self.assertIn("tab_id", inspect.inputSchema["required"])

    def test_url_redaction(self):
        self.assertEqual(public_url("https://user:secret@example.com/a?code=123#token"), "https://example.com/a")


@unittest.skipUnless(os.environ.get("BROWSER_MCP_LIVE_TEST") == "1", "Requires existing Chrome on 9222")
class LiveMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_connection_tabs_and_disconnect_preserves_chrome(self):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "browser_mcp"],
            cwd=str(Path(__file__).parent),
            env={**os.environ, "BROWSER_MCP_CDP_PORT": "9222", "BROWSER_MCP_ALLOW_ACTIONS": "1"},
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = await client.list_tools()
                self.assertGreaterEqual(len(tools.tools), 37)
                connected = await client.call_tool("connect_browser", {"prefer_websocket": True})
                self.assertFalse(connected.isError)
                self.assertTrue(json.loads(connected.content[0].text)["connected"])
                await client.call_tool("disconnect_browser", {"force": True})


if __name__ == "__main__":
    unittest.main()