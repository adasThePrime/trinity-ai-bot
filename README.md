# Trinity AI - Telegram Bot

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

An AI-powered Telegram bot built with [aiogram](https://docs.aiogram.dev/) and [uvloop](https://github.com/MagicStack/uvloop) that supports real-time web search, currency conversion, timezone lookups, streaming responses, inline queries, MongoDB user/rate-limit caching, and an optional maintenance mode.

>[!NOTE]
> - `uvloop` requires Python 3.12 or later.
> - If `uvloop` is unavailable, bot falls back to `asyncio`.

## Setup

### 1. Clone & install

```bash
git clone https://github.com/adasThePrime/trinity-ai-bot.git
cd trinity-ai-bot
pip install -r requirements.txt
```

### 2. Start the ddgs search server

The bot uses the [ddgs API server](https://github.com/deedy5/ddgs#api-server-with-mcp-integration) for web searches. Start it before running the bot:

```bash
ddgs api                                  # default: localhost:8000
ddgs api --host 127.0.0.1 --port 9000     # custom host/port
ddgs api --proxy socks5h://127.0.0.1:9150 # with proxy
```

> If you use Docker, the server starts automatically inside the container.

### 3. Configure

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```
| Variable             | Required | Description                                                         |
|----------------------|----------|---------------------------------------------------------------------|
| `BOT_TOKEN`          | Yes      | Telegram bot token from [@BotFather](https://t.me/BotFather)        |
| `OPENROUTER_API_KEY` | Yes*     | [OpenRouter](https://openrouter.ai/) API key                        |
| `USE_ZAI`            | No       | Enable ZAI alternative AI provider.                                 |
| `HTTPX_PROXY_URL`    | No       | Proxy for httpx clients — `http://`, `https://`, or `socks5://` URL |
| `DDGS_API_URL`       | No       | ddgs server URL (default `http://localhost:8000`)                   |
| `MONGO_URI`          | No       | MongoDB connection URI (default `mongodb://localhost:27017`)        |
| `ADMIN_IDS`          | No       | Comma-separated Telegram admin user IDs (empty = no admins)         |

*\*Required when using OpenRouter backend (default).*

### 4. Run

```bash
python -m bot
```

### Docker

```bash
docker build -t trinity-bot .
docker run --env-file .env trinity-bot
```

## Configuration

- `BOT_TOKEN` (*required*, `str`) - Telegram bot token from [@BotFather](https://t.me/BotFather).
- `TYPING_STATUS_INTERVAL` (*optional*, `float`) - Interval (seconds) for sending typing status.
- `STREAM_ENABLED` (*optional*, `bool`) - Enable streaming responses.
- `STREAM_DRAFT_INTERVAL` (*optional*, `float`) - Interval (seconds) between draft updates.
- `STREAM_CHUNK_SIZE` (*optional*, `int`) - Characters per stream chunk.
- `INLINE_QUERY_ENABLED` (*optional*, `bool`) - Enable inline queries.
- `ADMIN_IDS` (*optional*, `list[int]`) - Comma-separated list of admin Telegram user IDs.
- `MAINTENANCE_MODE` (*optional*, `bool`) - Enable maintenance mode to block all users, including admins.
- `MAINTENANCE_MESSAGE` (*optional*, `str`) - Message shown to users during maintenance.
- `MONGO_URI` (*optional*, `str`) - MongoDB connection URI.
- `MONGO_DB_NAME` (*optional*, `str`) - MongoDB database name.
- `CACHE_MAX_USERS` (*optional*, `int`) - Maximum users to cache in memory.
- `RATE_LIMITS_DB_THRESHOLD` (*optional*, `int`) - Minimum cooldown (seconds) to store rate limits in DB.
- `HTTPX_PROXY_URL` (*optional*, `str`) - Proxy URL for HTTP requests.
- `OPENROUTER_API_KEY` (*optional*, `str`) - OpenRouter API key for AI responses.
- `OPENROUTER_TIMEOUT` (*optional*, `int`) - Request timeout in seconds.
- `OPENROUTER_BASE_URL` (*optional*, `str`) - OpenRouter API endpoint.
- `OPENROUTER_DEFAULT_MODEL` (*optional*, `str`) - Default OpenRouter model.
- `USE_ZAI` (*optional*, `bool`) - Enable ZAI alternative AI provider.
- `ZAI_TIMEOUT` (*optional*, `int`) - ZAI request timeout in seconds.
- `ZAI_DEFAULT_MODEL` (*optional*, `str`) - Default ZAI model name.
- `MAX_TOOL_ROUNDS` (*optional*, `int`) - Maximum tool calls per request.
- `MAX_CONTEXT_MESSAGES` (*optional*, `int`) - Maximum messages to keep in context.
- `MAX_CONTEXT_CHARS` (*optional*, `int`) - Maximum characters in context.
- `MAX_SEARCH_RESULTS` (*optional*, `int`) - Maximum web search results to return.
- `DDGS_TIMEOUT` (*optional*, `int`) - DDGS search timeout in seconds.
- `DDGS_MAX_RETRIES` (*optional*, `int`) - Maximum retry attempts for DDGS.
- `DDGS_RETRY_DELAY` (*optional*, `float`) - Delay between retries in seconds.
- `DDGS_API_URL` (*optional*, `str`) - DDGS API server address.
- `MAX_TIMEZONES_PER_CALL` (*optional*, `int`) - Maximum timezones per lookup.
- `FRANKFURTER_BASE_URL` (*optional*, `str`) - Frankfurter API endpoint.
- `MAX_CURRENCY_SYMBOLS` (*optional*, `int`) - Maximum currency symbols per conversion.
- `LOG_LEVEL` (*optional*, `str`) - Logging level: DEBUG, INFO, WARNING, ERROR.
- `LOG_LEVEL_<name>` (*optional*, `str`) - Per-logger level overrides. Replace `<name>` with the logger's name (case-sensitive). For example, `LOG_LEVEL_httpx=WARNING`.

## Access Control

The bot supports an approval-based access system through the database. When approve-only mode is enabled, only approved users and admins can interact with the bot.

Set `ADMIN_IDS` to define bot administrators. Admins bypass the approval system and do not have any rate limits applied. Approved users can also be configured with different rate limits.

```env
# single admin
ADMIN_IDS=123456789

# multiple admins
ADMIN_IDS=123456789,987654321
```

## Project Structure

```
bot/
├── __main__.py          # Entry point
├── config.py            # All configuration
├── middlewares.py       # Bot middlewares
├── handlers/
│   ├── commands.py      # Command handlers
│   ├── chat.py          # Message handling (private + group)
│   ├── callbacks.py     # Callback query handlers
│   └── inline.py        # Inline query handlers
├── services/
│   ├── tools.py         # Tool schemas, dispatch, formatters
│   ├── ai.py            # OpenRouter API client
│   ├── zai.py           # Z.AI API client
│   ├── search.py        # Web search via ddgs API server
│   ├── currency.py      # Frankfurter API client
│   ├── time.py          # Timezone service
│   ├── http.py          # Shared httpx client manager
│   ├── streaming.py     # Message draft streaming
│   ├── access.py        # Access control logic
│   ├── cache.py         # In-memory caching logic
│   ├── db.py            # MongoDB database interactions
│   ├── rate_limit.py    # Rate limiting logic
│   └── typing.py        # Chat typing actions
└── utils/
    ├── context.py       # Per-chat conversation history
    ├── formatting.py    # Markdown -> MessageEntity parser
    ├── prompts.py       # System prompt builder
    ├── auth.py          # Authentication utilities
    ├── errors.py        # Error handling utilities
    └── messages.py      # Message building utilities
```

## Commands

**User Commands:**
```
start - Ping the bot
help - Show help message
clear - Clear conversation history
settings - Bot settings
privacy - Privacy policy
```

**Admin Commands:**
```
approve - Approve a user/group
disapprove - Disapprove a user/group
approveonly - Toggle approve-only mode
clearcache - Clear and reload the cache
```

## Scripts

The `scripts/` directory contains helpful utility tools:

- `set_commands.py`: Automates setting the bot commands in Telegram (for regular users and admins). Load the environment via `.env` file first.
  - Usage: `python scripts/set_commands.py`
  - Arguments:
    - `--clear`: Clear all custom commands and reset to default.
    - `--users-only`: Only set commands for regular users.
    - `--admins-only`: Only set commands for admins.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.