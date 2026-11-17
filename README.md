# chrome-persistent-mcp

Pure Python MCP server (`browser_mcp.py`) that attaches to an already-running Chrome browser over a **single, deterministically enforced persistent WebSocket Chrome DevTools Protocol (CDP) connection** (`ws://127.0.0.1:9222/devtools/browser/<id>`).

It enables any AI agent (Claude Code, Cursor, VS Code Copilot, Windsurf, or custom MCP clients) to operate seamlessly on your existing, signed-in Chrome window with **37 Playwright and DevTools tools**—including real-time Console log streaming, Network tab & WebSocket frame inspection, live DOM manipulation, accessibility snapshots, storage inspection, and browser automation—**without repeatedly prompting you to click "Allow/Approve" in Chrome**.

---

## Why Deterministic Persistent WebSocket Enforcement Exists

Modern Chrome (136+) displays a manual **"Allow debugging connection?"** confirmation prompt every time a new CDP WebSocket handshake is opened. AI agents frequently trigger repeated approval popups because they:
1. Try to call browser tools without establishing or maintaining a persistent WebSocket session,
2. Call `connect_browser` / `disconnect_browser` repeatedly between turns, or
3. Spawn ephemeral one-off processes (`curl http://127.0.0.1:9222`, `python -c ...`) that connect and immediately exit.

`chrome-persistent-mcp` solves this **deterministically** inside `browser_mcp.py`:

### 1. Mandatory Persistent WebSocket Gate (`require_persistent_websocket`)
Agents **cannot** skip the WebSocket handshake. Calling any browser tool (`list_tabs`, `select_tab`, `inspect_page`, `get_console_logs`, `get_network_requests`, `modify_dom`, `click`, `fill`, `cdp_send`, etc.) before establishing a persistent WebSocket raises an immediate deterministic error:

```text
RuntimeError: You are trying to connect to MCP (calling `list_tabs`) without maintaining a persistent WebSocket connection (detected agent: 'claude-code', live_connection_uptime: 0.0s). You MUST NOT skip the WebSocket handshake or make stateless single-call probes. Call `connect_websocket(agent_id='<your-agent-name>')` or `connect_browser(prefer_websocket=True, agent_id='<your-agent-name>')` FIRST to establish a persistent `ws://127.0.0.1:<port>/devtools/browser/<id>` session, and keep that connection alive.
```

### 2. Agent Identification & Live Connection Uptime Telemetry (`detect_agent_identity`)
Every connection identifies the calling agent (`agent_id` passed explicitly or fingerprinted automatically from `CLAUDE_CODE`, `CURSOR_TRACE_ID`, `VSCODE_PID`, `MCP_CLIENT_NAME`, or parent PID `ppid`) and tracks:
- **`connection_uptime_seconds` & `connection_uptime_human`**: Exact duration the agent has maintained the live WebSocket connection (e.g. `"4m 18s"`).
- **`tool_calls_on_connection`**: Number of MCP tool calls multiplexed over the current WebSocket handshake.
- **`handshake_count` & `redundant_connect_attempts`**: Detects if an agent tries to call `connect_websocket` / `connect_browser` again while already connected, returning the existing connection with a warning instead of opening a second CDP socket.
- **Cross-Process Churn Detection**: Tracks connection handshakes in a local state file (`chrome_persistent_mcp_9222.json`) and warns if an agent process is repeatedly opening short-lived connections within 60 seconds.

### 3. Disconnect Protection (`BROWSER_MCP_KEEP_WEBSOCKET_ALIVE=1`)
If an agent calls `disconnect_browser()` at the end of a task without `force=True`, the server blocks the disconnect so the WebSocket stays open for your next prompt:

```text
You are trying to close the MCP connection instead of maintaining a persistent WebSocket connection (agent='claude-code', live for 3m 12s). Disconnecting forces the user to re-approve Chrome on the next tool call. Keep this persistent WebSocket connection alive.
```

### 4. Cached `Page -> targetId` Mapping (Zero Per-Call CDP Re-Probing)
Once a tab's `targetId` is resolved, `BrowserHandler` caches the `Page` handle and attaches persistent Playwright event listeners (`console`, `pageerror`, `request`, `response`, `requestfailed`, `websocket`, `dialog`) so subsequent tool calls never open/detach temporary CDP sessions.

---

## Required Agent Workflow

1. **Step 1 — Establish Persistent WebSocket Once**:
   Call `connect_websocket(agent_id="your-agent-name")` (or `connect_browser(prefer_websocket=True, agent_id="your-agent-name")`).
2. **Step 2 — Discover & Select Existing Tab**:
   Call `list_tabs()` and `select_tab(tab_id)` to bind to the user's open Chrome tab.
3. **Step 3 — Multiplex All Inspection & Automation Calls Over the Live WebSocket**:
   Call any of the 37 tools below without reconnecting or calling `disconnect_browser()`.

---

## Complete Pure-Python Playwright & DevTools Tool Surface (37 Tools)

| Category | Tools | Purpose |
| :--- | :--- | :--- |
| **Persistent WebSocket & Session** | `connect_websocket`, `connect_browser`, `connection_status`, `disconnect_browser` | Establish/reuse the persistent `ws://` connection, inspect agent identity & live connection uptime, and guard against premature disconnects. |
| **Tab Management** | `list_tabs`, `select_tab`, `manage_tabs` | List open Chrome tabs with sanitized URLs, select a target tab, or run `new`, `close`, `activate`, `reload`, `go_back`, `go_forward`. |
| **Console Tab Inspection** | `get_console_logs`, `clear_console_logs` | Stream and filter real-time `console.log`, `info`, `warn`, `error`, and uncaught `pageerror` exceptions captured over the persistent WebSocket. |
| **Network Tab & WebSocket Frames** | `get_network_requests`, `get_network_response_body`, `clear_network_requests`, `get_websocket_frames`, `route_network` | Inspect live HTTP/XHR/Fetch traffic, status codes, headers, decoded response bodies, page WebSocket frames, and mock/abort requests. |
| **DOM & Accessibility Inspection** | `inspect_page`, `accessibility_snapshot`, `query_selector_all`, `modify_dom`, `get_computed_styles`, `evaluate_js` | Capture ARIA accessibility trees, query all matching selectors with bounding rects, mutate live DOM nodes (`set_text`, `set_html`, `set_attribute`, `remove_attribute`, `add_class`, `remove_class`, `set_style`, `remove`), inspect computed styles, and evaluate JS. |
| **Playwright Interactions** | `navigate`, `click`, `fill`, `select_option`, `press_key`, `hover`, `drag_and_drop`, `wait_for_selector`, `handle_dialog`, `upload_file` | Full Playwright user interaction suite on the existing Chrome tab (blocks direct password injection via `fill`). |
| **Storage, Artifacts & Raw CDP** | `screenshot`, `get_storage_state`, `set_storage_item`, `save_pdf`, `start_tracing`, `stop_tracing`, `cdp_send` | Capture viewport/full-page/element PNG screenshots, inspect cookie metadata & `localStorage`/`sessionStorage`, export PDFs, record Playwright traces, and send raw CDP commands (`<Domain>.<method>`) over the tab's persistent `CDPSession`. |

---

## Installation

Requires Python 3.11+ (`mcp` and `playwright` Python packages only; zero Node.js or npm dependencies):

```powershell
git clone https://github.com/ayush1920/chrome-persistent-mcp.git
cd chrome-persistent-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Or install directly from GitHub:

```powershell
pip install git+https://github.com/ayush1920/chrome-persistent-mcp.git
```

---

## Starting Chrome with Remote Debugging

Launch Chrome with a dedicated profile directory and loopback debugging port `9222`:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="C:\BrowserProfiles\my-profile" --profile-directory="Default"
```

- If Chrome is configured via `chrome://inspect` / `DevToolsActivePort`, set `BROWSER_MCP_USER_DATA_DIR` or `BROWSER_MCP_DEVTOOLS_ACTIVE_PORT` in `.vscode/mcp.json`.
- Approve Chrome's debugging prompt **once** when `connect_websocket` first attaches; the persistent WebSocket remains open across all subsequent agent tasks.

---

## VS Code / MCP Client Configuration (`.vscode/mcp.json`)

```json
{
  "servers": {
    "existing-chrome-mcp": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["-m", "browser_mcp"],
      "cwd": "${workspaceFolder}",
      "env": {
        "BROWSER_MCP_CDP_PORT": "9222",
        "BROWSER_MCP_ALLOW_ACTIONS": "1",
        "BROWSER_MCP_KEEP_WEBSOCKET_ALIVE": "1"
      }
    }
  }
}
```

---

## Running Unit Tests

```bash
python3 -m unittest -v
```