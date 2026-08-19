"""`nblm-mcp-login` — capture Google session cookies for the MCP server.

Login is deliberately a separate command rather than an MCP tool: it opens a
real browser window and needs a human at the keyboard, which an MCP host
cannot provide. It delegates to notebooklm-py's own `notebooklm login`, so the
cookies land where `NotebookLMClient.from_storage()` looks for them and stay
compatible with that project's profile layout.
"""

from __future__ import annotations

import subprocess
import sys

USAGE = """\
Usage: nblm-mcp-login [--profile NAME] [extra notebooklm login flags]

Opens a browser, waits for you to sign in to NotebookLM, and stores the
session cookies under ~/.notebooklm/. Run it once before starting the MCP
server, and again whenever auth_status reports the session expired.

Requires the browser extra:  pip install "nblm-mcp[auth]"
"""


def login_main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print(USAGE)
        return 0

    command = [sys.executable, "-m", "notebooklm", "login", *args]
    try:
        return subprocess.call(command)
    except FileNotFoundError:
        print(
            "Could not run notebooklm-py. Install it with:\n"
            '  pip install "nblm-mcp[auth]"',
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(login_main())
