# Slack MCP Server

An MCP server that lets you interact with Slack from Claude Code or any MCP client. Each user authenticates with their own Slack account via OAuth — all actions are performed as the authenticated user using **user tokens (xoxp)**.

## Features

- **Per-user OAuth** — authenticate with your own Slack identity
- **User tokens (xoxp)** — messages appear as sent by you, search works correctly
- **Multi-workspace** — connect to multiple Slack workspaces
- **13 tools** — messaging, channels, threads, files, search, reactions, workspace management

## Prerequisites

1. Create a Slack app at https://api.slack.com/apps
2. Set redirect URL to `http://localhost:9876/callback`
3. Add **User Token Scopes** (not bot scopes):
   - `channels:read`, `groups:read` — list channels
   - `channels:history`, `groups:history` — read history
   - `chat:write` — post messages
   - `search:read` — search messages
   - `reactions:write`, `reactions:read` — reactions
   - `users:read` — user info
   - `files:read` — download shared files
4. Note your Client ID and Client Secret

## Setup

```bash
# Clone and install
git clone <repo-url>
cd slack-mcp-server
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your SLACK_CLIENT_ID and SLACK_CLIENT_SECRET
```

## Usage with Claude Code

### Option A: OAuth (recommended for teams)

```bash
claude mcp add slack \
  -e SLACK_CLIENT_ID=your-client-id \
  -e SLACK_CLIENT_SECRET=your-client-secret \
  -- uv --directory /path/to/slack-mcp-server run slack-mcp-server
```

Then in Claude Code, ask to "authenticate with Slack" — it will open the browser for OAuth.

### Option B: Direct token (personal use)

```bash
claude mcp add slack \
  -e SLACK_USER_TOKEN=xoxp-your-token \
  -- uv --directory /path/to/slack-mcp-server run slack-mcp-server
```

### After setup

Restart Claude Code, then use tools like `post_message`, `search_messages`, `list_channels`, etc.

## Tools

| Tool | Description |
|------|-------------|
| `slack_authenticate` | Connect your Slack account via OAuth |
| `slack_list_workspaces` | List connected workspaces |
| `slack_set_default_workspace` | Set the default workspace |
| `slack_remove_workspace` | Disconnect a workspace |
| `post_message` | Post a message to a channel |
| `reply_to_thread` | Reply in a thread |
| `list_channels` | List workspace channels |
| `get_channel_history` | Read channel message history |
| `get_thread_replies` | Read a thread: parent message and replies |
| `get_file` | Download a shared file into `~/Downloads/slack-mcp`; first 64 KB of text files returned inline |
| `search_messages` | Search messages across the workspace |
| `add_reaction` | Add an emoji reaction |
| `remove_reaction` | Remove an emoji reaction |

## Development

```bash
uv run pytest              # Run tests
uv run ruff check src/     # Lint
uv run mcp dev src/slack_mcp_server/server.py  # MCP Inspector
```

## Upgrading: files:read

`get_file` needs the `files:read` user scope. Installations authorized before it was added keep
working for every other tool; to read files, add `files:read` to the Slack app's User Token
Scopes and run `slack_authenticate` again (or regenerate the `xoxp` token in direct token mode).

`get_file` only sends the token to `https://*.slack.com`, following redirects by hand while they stay
there. Files stored outside Slack (Google Drive, Dropbox) and native Slack documents (canvas, posts)
are not downloaded; their link is returned. Downloads are capped at 100 MB and written atomically.
