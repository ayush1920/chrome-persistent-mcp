# Mandatory Agent Instructions for Chrome Persistent MCP

## Stop Probing Port 9222 — Reuse the Persistent WebSocket MCP Tools

1. **NEVER probe `127.0.0.1:9222` from the terminal or shell**:
   - Do **not** run `curl http://127.0.0.1:9222/json/version`, `Invoke-WebRequest`, `python -c "...connect_over_cdp..."`, `node`, or `npx playwright` in a terminal to check if Chrome is running.
   - **Why**: Every new process that connects to Chrome's debugging endpoint opens a brand-new WebSocket handshake, which forces Chrome to display a manual **"Allow debugging connection?"** popup to the user.
2. **Use ONLY the `existing-chrome-mcp` MCP tools**:
   - The `existing-chrome-mcp` server (`browser_mcp.py`) maintains a **single, persistent WebSocket (`ws://127.0.0.1:9222/devtools/browser/<id>`)** for the entire lifetime of the IDE session.
   - Every tool call (`list_tabs`, `select_tab`, `get_console_logs`, `get_network_requests`, `modify_dom`, `evaluate_js`, `click`, `fill`, `screenshot`, `cdp_send`, etc.) multiplexes over that already-approved WebSocket connection with **zero** new connection prompts.
3. **NEVER call `disconnect_browser` between tasks**:
   - Leave the MCP connection open after finishing your task so subsequent prompts reuse the exact same approved WebSocket session.
