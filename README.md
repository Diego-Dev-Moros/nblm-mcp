# nblm-mcp

An MCP server that gives an AI agent access to **Google NotebookLM** (rebranded
*Gemini Notebook* in July 2026): list and create notebooks, manage their
sources, ask questions that are answered **from those sources with citations**,
and generate Studio artifacts like audio overviews, briefing docs, quizzes and
mind maps.

The point is grounding. NotebookLM answers only from the material you gave it,
so an agent that can call `ask` gets cited answers out of your own documents
instead of guessing — and it costs no tokens of your own context, because
Gemini does the reading server-side.

> ### ⚠️ Unofficial — read this first
>
> **Google has no public consumer API for NotebookLM.** This server drives the
> same private web endpoints the notebooklm.google.com UI calls, authenticated
> with your own browser session cookies, via the MIT-licensed
> [`notebooklm-py`](https://github.com/teng-lin/notebooklm-py) library.
>
> - Not affiliated with or endorsed by Google.
> - The internal API can change without notice and break this server.
> - Your Google account's rate limits and daily Studio quotas apply.
> - Use an account you are comfortable automating. Best for personal
>   projects, research, and prototypes.
>
> Google *does* document an official API for **Gemini Notebook Enterprise**. If
> you have a Workspace/Cloud org with that feature, prefer it over this.

## Install

Not on PyPI yet — install straight from this repository. `uvx` builds and runs
it on demand, so there is nothing to keep updated by hand:

```bash
uvx --from git+https://github.com/Diego-Dev-Moros/nblm-mcp nblm-mcp
```

## Log in once

Login needs the `auth` extra (Playwright) and a human at the keyboard:

```bash
uvx --from "nblm-mcp[auth] @ git+https://github.com/Diego-Dev-Moros/nblm-mcp" nblm-mcp-login
```

A browser window opens; sign in to NotebookLM as you normally would. The
session cookies are stored under `~/.notebooklm/` (the same profile layout
`notebooklm-py` uses, so an existing `notebooklm login` also works). The MCP
server never logs in on its own — it needs an interactive browser, which an
MCP host cannot provide.

If Playwright has no browser yet, run `playwright install chromium` first.

Cookies expire. When they do, tools start returning an auth error; run the
login command again.

## Connect it to a client

**Claude Code** — `-s user` makes it available in every project:

```bash
claude mcp add notebooklm -s user -- \
  uvx --from git+https://github.com/Diego-Dev-Moros/nblm-mcp nblm-mcp
```

**Claude Desktop** — add this to `claude_desktop_config.json` and restart the
app (macOS: `~/Library/Application Support/Claude/`, Windows:
`%APPDATA%\Claude\`, Linux: `~/.config/Claude/`):

```json
{
  "mcpServers": {
    "notebooklm": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Diego-Dev-Moros/nblm-mcp", "nblm-mcp"]
    }
  }
}
```

Claude Desktop launches from the GUI, which does not inherit your shell's
`PATH`. If the server fails to start there, replace `"uvx"` with its absolute
path (`which uvx`, typically `~/.local/bin/uvx`).

Either way, confirm it works by asking the agent to call `auth_status`.

## Tools

| Tool | What it does |
|---|---|
| `auth_status` | Verifies the stored session with a real request; tells you if you need to log in again. |
| `list_notebooks` | All notebooks the account can reach, with ids and source counts. |
| `get_notebook` | One notebook plus its sources; optionally NotebookLM's own summary. |
| `create_notebook` | Creates an empty notebook. |
| `delete_notebook` | Deletes a notebook and everything in it. Requires `confirm=true`. |
| `list_sources` | Sources in a notebook and their processing status. |
| `add_source` | Adds one source from a URL (web, YouTube, Drive), pasted text, or a local file. |
| `delete_source` | Removes a source. Requires `confirm=true`. |
| `ask` | Asks the notebook a question; returns the answer plus citations resolved to source titles. |
| `chat_history` | Past question/answer turns for the notebook's conversation. |
| `list_artifacts` | Generated Studio artifacts and their status — also how you poll a running generation. |
| `generate_artifact` | Generates audio, video, report, study_guide, quiz, flashcards, infographic, slide_deck, or mind_map. |
| `download_artifact` | Downloads a completed artifact to a file on the machine running the server. |

### Notes on behavior

- **Destructive tools are gated.** `delete_notebook` and `delete_source`
  refuse to run without `confirm=true`, so a stray tool call can't destroy a
  notebook.
- **Generation is slow and quota-bound.** `generate_artifact` returns as soon
  as the job is queued (`wait=false`, the default) and tells the agent to poll
  `list_artifacts`. Pass `wait=true` to block instead; it waits up to
  `NBLM_GENERATION_TIMEOUT` seconds.
- **File paths are server-side.** `add_source(file_path=...)` and
  `download_artifact` read and write on the host running the MCP server, which
  is not necessarily where the user's chat client runs.

## Configuration

All optional — see [`.env.example`](.env.example). A `.env` in the working
directory is loaded if present.

| Variable | Default | Purpose |
|---|---|---|
| `NOTEBOOKLM_PROFILE` | active profile | Which stored login to use, for multiple Google accounts. |
| `NOTEBOOKLM_STORAGE_PATH` | resolved from profile | Explicit path to a `storage_state.json`. |
| `NBLM_DOWNLOAD_DIR` | `~/.nblm-mcp/downloads` | Where `download_artifact` writes by default. |
| `NBLM_GENERATION_TIMEOUT` | `600` | Seconds to wait for an artifact when `wait=true`. |
| `NBLM_SOURCE_TIMEOUT` | `180` | Seconds to wait for a new source to finish processing. |

## Development

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest
uv run ruff check src tests
```

The test suite runs the tools against an in-memory fake client — it never
touches Google, so it is safe and fast to run anywhere.

## Prior art

[`notebooklm-py`](https://github.com/teng-lin/notebooklm-py) does the hard part
— reverse-engineering and maintaining the private `batchexecute` protocol — and
ships its own, larger MCP server. This project is a smaller, opinionated tool
surface on top of that library: fewer tools, confirmation gates on destructive
operations, and citation-resolved answers.

## License

MIT — see [LICENSE](LICENSE).
