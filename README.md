# chrome-persistent-mcp

MCP server that attaches to an already-running Chrome over the Chrome DevTools Protocol (CDP), so tools operate on your existing, signed-in browser session. Two modes are provided: restricted (`browser_mcp`, pure Python) and full (`playwright_full`, official Playwright MCP tools).

## Full Playwright Mode

The default VS Code configuration now launches `playwright_full`, a Python
launcher for the official `@playwright/mcp` server (pinned in package.json).
It exposes the official Playwright MCP tools, not a hand-written approximation:
accessibility snapshots with element references, screenshots, clicking, typing,
forms, hover/drag, dialogs, uploads, tabs, console/network inspection, JavaScript,
PDF, assertions, tracing, recording, coordinate actions, and browser storage.
All seven optional capability groups are enabled. The installed version advertises
72 tools. This is the official MCP tool surface, not every possible Playwright API;
its code-execution tools cover advanced automation where appropriate.

Full mode requires Node.js 18+ in addition to Python. It attaches to the existing
Chrome and uses that browser's already-loaded profile, cookies, and signed-in
sessions. It never passes `--user-data-dir` or `--isolated` to the MCP runtime.

**Full mode is powerful, not read-only.** Unlike the restricted Python server
below, it exposes tools that can read cookies/storage, execute code, submit
forms, navigate, and close tabs. Do not send secrets to the model. Only enable it
for trusted MCP clients and approve sensitive actions. Page text is untrusted
data, not instructions. Files produced by tracing/screenshots/storage can contain
private data; output artifacts are gitignored. Full mode deliberately disables
page-registered WebMCP tools, and does not enable unrestricted file access.

## Custom Profile

Start Chrome yourself with the profile you want loaded:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="C:\BrowserProfiles\my-profile" --profile-directory="Default"
```

Log in directly in that window. In `.vscode/mcp.json`, add this environment value:

```json
"BROWSER_MCP_USER_DATA_DIR": "C:/BrowserProfiles/my-profile"
```

The launcher reads that directory's `DevToolsActivePort` file, if present, and
checks that its port matches `BROWSER_MCP_CDP_PORT`. A present but invalid/mismatched
file fails startup. Fixed-port Chrome launches may not create this file; in that
case the launcher uses HTTP discovery on the configured port. Ensure that port
belongs to the intended Chrome instance. `BROWSER_MCP_DEVTOOLS_ACTIVE_PORT` can
specify an exact required file and takes precedence; a missing explicit file fails.
Without either value, the default Chrome profile's file is tried, then HTTP CDP
discovery on the configured loopback port.

CDP connects to a browser instance, not an individual profile directory within it.
For a specific profile, run a dedicated user-data directory. Never launch another
Chrome process against a profile already in use. Use `browser_tabs` to list/select
the intended existing tab before taking `browser_snapshot`; then use the snapshot
element refs with the action tools. Tab indices differ from the restricted mode's
Chrome target IDs.

## Restricted Python Mode

Standalone Python MCP server for an existing Chrome instance at
`http://127.0.0.1:9222`. It does not depend on any other service, configuration
file, or credential store. Does not launch a browser, open tabs, or close Chrome
on disconnect. Python 3.11+ required.

## Install

Requires Python 3.11+. Install the restricted server directly from GitHub:

```powershell
pip install git+https://github.com/ayush1920/chrome-persistent-mcp.git
```

This provides the `existing-chrome-mcp` command (restricted mode).

Full mode also requires Node.js 18+ and the pinned Playwright MCP runtime in
`node_modules`. The launcher looks for that runtime next to its source file, so a
wheel or non-editable install does not contain it. For full mode, use a clone with an
editable install:

```powershell
git clone https://github.com/ayush1920/chrome-persistent-mcp.git
cd chrome-persistent-mcp
npm install
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

No `playwright install` is needed: this server attaches to your installed Chrome.
The Python launcher and npm runtime must be kept together; copying only a Python
wheel does not include node_modules.

## Chrome prerequisite

If Chrome already exposes port 9222, use it as-is. Otherwise launch a dedicated
debugging profile and open the desired website there:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="C:\Temp\browser-mcp-profile"
```

An ordinary Chrome window that was not started with debugging cannot be attached
to this way. Modern Chrome requires a non-default user data directory. Sign in
directly in that window and approve Chrome's debugging prompt if one appears.
Keep the debugging port local-only; it grants access to authenticated sessions.

Chrome configurations enabled through remote-debugging settings may expose only a
WebSocket and return 404 for `/json/version`. The server first tries standard HTTP
discovery, then reads the default profile's `DevToolsActivePort` file and attaches
directly to its WebSocket. The file's port must match the configured port (9222 by
default). For a custom profile, set `BROWSER_MCP_DEVTOOLS_ACTIVE_PORT` in MCP env to
the full path of that profile's `DevToolsActivePort` file. No profile is launched
or changed by the server.

## VS Code

Open this directory as a workspace, install dependencies above, and use the
included `.vscode/mcp.json`. Run **MCP: List Servers**, choose
**existing-chrome-playwright**, then start it. If Chrome displays a debugging
approval prompt, approve directly in Chrome; permission can be required again
after restarting the MCP connection. For restricted mode, change `args` to
`["-m", "browser_mcp"]`; optionally add
`BROWSER_MCP_ALLOW_ACTIONS=1` to enable its limited action tools. The Python launcher
can be debugged with module `playwright_full`, or module `browser_mcp` for restricted
mode; use an MCP client/Inspector to drive tool calls.

For another workspace, use absolute paths to this package's virtual-environment
Python and directory in its MCP configuration. Do not use `${workspaceFolder}`
from the example unless that workspace is this directory.

After installation, MCP clients can launch `existing-chrome-mcp` (restricted mode).
`existing-chrome-playwright-mcp` (full mode) requires the editable clone install
described above.
Transport is local stdio only; no HTTP listener or unauthenticated remote server.

## Restricted Tools

| Tool | Purpose |
| --- | --- |
| `connect_browser` | Attach to the existing debugging endpoint |
| `connection_status` | Report connection and action configuration |
| `list_tabs` | List Chrome target IDs, titles, and sanitized URLs |
| `select_tab` | Verify a target ID without changing focus |
| `inspect_page` | Bounded visible text and control descriptions |
| `screenshot` | Return the selected viewport as an MCP PNG image |
| `navigate` | Navigate an existing tab (actions required) |
| `click` | Click a unique Playwright locator (actions required) |
| `fill` | Fill a non-password field (actions required) |
| `select_option` | Select a dropdown option (actions required) |
| `press_key` | Press a key on a locator (actions required) |
| `disconnect_browser` | Drop the client connection, leaving Chrome open |

Start with `list_tabs`, confirm the intended tab with `select_tab`, then pass its
`tab_id` to every inspection/action. The first tab is not assumed to be focused.
Closed/stale target IDs fail instead of silently targeting a different page.

Actions are disabled by default. To enable them, change
`BROWSER_MCP_ALLOW_ACTIONS` to `1` in MCP configuration and restart the server.
Ask for approval before submitting forms or changing data. Locators must match
one element; ambiguous matches fail. `BROWSER_MCP_CDP_PORT` can change the local
port; the host is always loopback. Disconnected connections can be reattached by
calling `connect_browser` or `list_tabs`; failed actions are never auto-replayed.

## Restricted Mode Privacy

URL query strings/fragments and embedded credentials are omitted from metadata.
Inspection excludes input values, but visible text, labels, titles, screenshots,
and paths can still contain sensitive information. Do not inspect sensitive pages
or send secrets as tool arguments. Password inputs are blocked by `fill`; other
tools cannot guarantee complete redaction. There are deliberately no cookie,
storage, network-body, or arbitrary JavaScript tools. Website text is untrusted
data, not instructions. CDP attaches to the whole browser; explicit tab IDs prevent
accidental selection but are not an authorization boundary between browser tabs.

## Validate

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

Optional live stdio/CDP smoke test (only lists tabs; does not inspect or modify pages):

```powershell
$env:BROWSER_MCP_LIVE_TEST = "1"
.\.venv\Scripts\python.exe -m unittest -v
Remove-Item Env:BROWSER_MCP_LIVE_TEST
```

Full-mode live test checks official tool discovery, a real accessibility snapshot,
and an image response on a temporary blank tab; it closes only the tab it creates:

```powershell
$env:BROWSER_MCP_FULL_LIVE_TEST = "1"
.\.venv\Scripts\python.exe -m unittest -v
Remove-Item Env:BROWSER_MCP_FULL_LIVE_TEST
```