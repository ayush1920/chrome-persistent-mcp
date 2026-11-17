# CLAUDE.md — Persistent Chrome WebSocket MCP Protocol

## Critical Rule: Never Probe Port 9222 via Bash/Terminal

- **DO NOT** run `curl http://127.0.0.1:9222`, one-off Python scripts (`connect_over_cdp`), or `playwright` CLI commands in bash. Every separate process that touches port `9222` or `DevToolsActivePort` opens a new CDP connection and forces the user to manually click **"Approve"** in Chrome.
- **ALWAYS** use the `existing-chrome-mcp` MCP server tools directly (`list_tabs` -> `select_tab` -> `get_console_logs` / `get_network_requests` / `modify_dom` / `evaluate_js` / `click` / `fill` / `screenshot`).
- The MCP server holds **one persistent WebSocket connection (`ws://127.0.0.1:9222/devtools/browser/<id>`)** in memory and multiplexes all 37 Playwright & DevTools tools over that single approved socket.
- **NEVER** call `disconnect_browser` at the end of a turn; keep the persistent WebSocket alive across turns.
