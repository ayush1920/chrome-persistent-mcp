import os
import shutil
import subprocess
import sys
from pathlib import Path

from browser_mcp import BrowserHandler


def command() -> list[str]:
    root = Path(__file__).resolve().parent
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js 18+ is required for official Playwright MCP")
    cli = root / "node_modules/@playwright/mcp/cli.js"
    if not cli.is_file():
        raise RuntimeError(f"Run npm install in {root} to install the Playwright MCP runtime")
    profile = os.environ.get("BROWSER_MCP_USER_DATA_DIR")
    explicit_active_port = os.environ.get("BROWSER_MCP_DEVTOOLS_ACTIVE_PORT")
    active_port = explicit_active_port
    if profile and not active_port:
        active_port = str(Path(profile) / "DevToolsActivePort")
    handler = BrowserHandler(
        port=int(os.environ.get("BROWSER_MCP_CDP_PORT", "9222")),
        devtools_active_port=active_port,
    )
    websocket = handler.websocket_endpoint()
    if active_port and not websocket and (explicit_active_port or Path(active_port).is_file()):
        raise RuntimeError(
            "The selected profile's DevToolsActivePort file is missing or does not match "
            "BROWSER_MCP_CDP_PORT. Start that Chrome profile with remote debugging first."
        )
    return [
        node, str(cli),
        "--cdp-endpoint", websocket or handler.endpoint,
        "--caps", "vision,pdf,devtools,testing,network,storage,config",
        "--output-dir", str(root / "artifacts"),
        "--no-webmcp",
    ]


def main() -> None:
    try:
        args = command()
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    process = subprocess.Popen(args)
    try:
        raise SystemExit(process.wait())
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()


if __name__ == "__main__":
    main()