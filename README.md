# chrome-persistent-mcp

Pure Python MCP server (`browser_mcp.py`) that attaches to an already-running Chrome browser over a **persistent WebSocket Chrome DevTools Protocol (CDP) connection** (`ws://127.0.0.1:9222/devtools/browser/<id>`), enabling any AI agent to operate seamlessly on your existing, signed-in Chrome window with full Playwright and DevTools capabilities: real-time Console log streaming, Network tab & WebSocket frame inspection, live DOM manipulation, accessibility snapshots, storage inspection, and browser automation.

## Architecture & Persistent WebSocket Bridge

1. **Persistent WebSocket Transport (`ws://127.0.0.1:<port>/devtools/browser/<id>`)**:
   - `BrowserHandler` resolves Chrome's WebSocket debugger endpoint via `DevToolsActivePort` or `http://127.0.0.1:9222/json/version` (`webSocketDebuggerUrl`) and maintains a persistent, full-duplex WebSocket connection.
   - Embedded MCP server `instructions` (`AGENT_INSTRUCTIONS`) explicitly instruct connecting agents to call `connect_browser(prefer_websocket=True)` or `connect_websocket()` once, verify `transport == "websocket"` via `connection_status`, and reuse the persistent session across all tool calls without closing the user's tabs on disconnect.
2. **Real-Time Tab Telemetry (`TabTelemetry`)**:
   - Selecting or listing tabs attaches persistent Playwright & CDP listeners (`console`, `pageerror`, `request`, `response`, `requestfailed`, `websocket`, `dialog`) and caches per-tab `CDPSession` instances (`cdp_send`).
   - Any agent can inspect historical and real-time console output (`get_console_logs`), Network tab traffic and response bodies (`get_network_requests`, `get_network_response_body`, `route_network`), and page WebSocket frames (`get_websocket_frames`).
3. **Full Pure-Python Playwright Tool Surface (37 Tools)**:
   - **Connection & Tabs**: `connect_browser`, `connect_websocket`, `connection_status`, `disconnect_browser`, `list_tabs`, `select_tab`, `manage_tabs` (`new`, `close`, `activate`, `reload`, `go_back`, `go_forward`)
   - **Console & Network Tab Inspection**: `get_console_logs`, `clear_console_logs`, `get_network_requests`, `get_network_response_body`, `clear_network_requests`, `get_websocket_frames`, `route_network`
   - **DOM Inspection & Manipulation**: `inspect_page`, `accessibility_snapshot`, `query_selector_all`, `modify_dom` (`set_text`, `set_html`, `set_attribute`, `remove_attribute`, `add_class`, `remove_class`, `set_style`, `remove`), `get_computed_styles`, `evaluate_js`
   - **Playwright Interaction & Artifacts**: `navigate`, `click`, `fill`, `select_option`, `press_key`, `hover`, `drag_and_drop`, `wait_for_selector`, `handle_dialog`, `upload_file`, `screenshot`, `save_pdf`, `start_tracing`, `stop_tracing`
   - **Storage & Raw CDP**: `get_storage_state`, `set_storage_item`, `cdp_send`

## Install & Run

Requires Python 3.11+ (`mcp` and `playwright` Python packages only; no Node.js or npm required):

```powershell
git clone https://github.com/ayush1920/chrome-persistent-mcp.git
cd chrome-persistent-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Start Chrome with remote debugging on loopback port `9222`:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="C:\BrowserProfiles\my-profile"
```

## Validate

```bash
python3 -m unittest -v
```