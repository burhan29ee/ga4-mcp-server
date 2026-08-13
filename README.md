# ga4-mcp-server

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server for **Google Analytics 4** with both **read and write** access. Connect it to Claude (or any MCP client) and pull reports, manage configuration, build remarketing audiences, and send server-side events — in natural language, using your own Google credentials. No third-party service, no subscription.

Most GA4 MCP servers are read-only. This one also **writes**: it can create custom dimensions and metrics, mark conversions, **create audiences** (for remarketing lists you can share to Google Ads), and manage/use the **Measurement Protocol**.

## Features

**Read**
- List accounts and properties, property details, and data streams
- Run GA4 reports (`run_report`) and realtime reports (`run_realtime_report`)
- List custom dimensions, custom metrics, key events (conversions), and audiences

**Write**
- Create and archive custom dimensions
- Create custom metrics
- Create key events (conversions)
- Create and archive **audiences** (e.g. everyone who fired `generate_lead` in the last 30 days)
- Create / list / delete **Measurement Protocol** API secrets
- **Send events** into a property via the Measurement Protocol (with a `validate=True` mode that checks the payload without ingesting it)

## Requirements

- **Python 3.10+** (the MCP SDK requires it)
- A Google Cloud project and a **service account** with a JSON key
- The service account granted access on your GA4 account/property (Viewer/Analyst for reads, **Editor** for writes)

## Google setup (one time)

1. In the [Google Cloud Console](https://console.cloud.google.com), create (or pick) a project.
2. Enable the **Google Analytics Data API** and the **Google Analytics Admin API** for that project.
3. Create a **service account** and download a **JSON key** for it.
4. In **Google Analytics → Admin → Account (or Property) access management**, add the service account's email (`...@your-project.iam.gserviceaccount.com`) as a user — **Editor** if you want write access.

That's it — no OAuth consent screen, no token refresh. The service account authenticates directly.

## Install

Using [uv](https://docs.astral.sh/uv/) (recommended — it manages an isolated Python for you):

```bash
git clone https://github.com/OWNER/ga4-mcp-server.git
cd ga4-mcp-server
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e .
```

Or with pip:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Configure your MCP client

Point the server at your service-account key with the `GOOGLE_APPLICATION_CREDENTIALS` environment variable, then add it to your client. For **Claude Desktop**, edit `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`; Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ga4": {
      "command": "/absolute/path/to/ga4-mcp-server/.venv/bin/python",
      "args": ["-m", "ga4_mcp_server.server"],
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/absolute/path/to/service-account-key.json"
      }
    }
  }
}
```

Restart the client. You should be able to ask things like *"list my GA4 properties,"* *"pull last 28 days of users and conversions by channel,"* or *"create a remarketing audience of everyone who registered for a webinar in the last 60 days."*

## Tool reference

| Tool | Type | What it does |
|------|------|--------------|
| `list_account_summaries` | read | List accounts and their properties |
| `get_property_details` | read | Property name, time zone, currency, industry |
| `list_data_streams` | read | Web/app streams and their measurement IDs |
| `run_report` | read | GA4 report by metrics/dimensions/date range |
| `run_realtime_report` | read | Realtime report (last ~30 min) |
| `list_custom_dimensions` | read | Custom dimensions on a property |
| `create_custom_dimension` | write | Create a custom dimension |
| `archive_custom_dimension` | write | Archive a custom dimension |
| `list_custom_metrics` | read | Custom metrics on a property |
| `create_custom_metric` | write | Create a custom metric |
| `list_key_events` | read | Key events (conversions) |
| `create_key_event` | write | Mark an event as a conversion |
| `list_audiences` | read | Audiences on a property |
| `create_event_audience` | write | Create an audience of users who fired an event |
| `archive_audience` | write | Archive an audience |
| `list_measurement_protocol_secrets` | read | MP API secrets for a stream |
| `create_measurement_protocol_secret` | write | Create an MP API secret |
| `delete_measurement_protocol_secret` | write | Delete an MP API secret |
| `send_ga4_event` | write | Send an event via the Measurement Protocol |

## Security

The service-account key is a credential — treat it like a password.

- **Never commit it.** The included `.gitignore` blocks `*.json` (except the example config), `.env`, and key files, but keep your key outside the repo anyway.
- Grant the service account the least access it needs (Viewer/Analyst if you only read).
- If a key is ever exposed, delete it in Google Cloud (IAM → Service Accounts → Keys) and create a new one.
- `send_ga4_event` writes data **into** your property. Use `validate=True` first to check payloads without ingesting them.

## Notes

- The `mcp` dependency is pinned to `>=1.2,<2`. The 2.0 SDK reorganized its API and removed `mcp.server.fastmcp`, which this server uses.
- Audiences use the GA4 Admin **v1alpha** API; the rest use the stable v1beta and Data APIs.
- This is an independent open-source project and is not affiliated with or endorsed by Google.

## License

[MIT](LICENSE)
