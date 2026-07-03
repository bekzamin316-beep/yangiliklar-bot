# Telegram Crypto News AI Bot

Production-ready Telegram bot that collects crypto news, analyzes it with AI, translates to Uzbek, and publishes to a Telegram channel.

## Features

- **Multi-source RSS Collection**: CoinDesk, CoinTelegraph, Binance, Bybit, OKX, KuCoin
- **AI Analysis**: Summarization, sentiment analysis, importance scoring
- **Multi-provider AI Support**: OpenRouter, Groq, Gemini, Claude, OpenAI, Ollama
- **Automatic Fallback**: Switches to backup providers if primary fails
- **Daily Digest**: Automated summary posts at configurable time
- **Admin Panel**: Full management via Telegram (AI settings, prompts, sources)
- **Duplicate Detection**: Prevents reposting identical news
- **Database Storage**: PostgreSQL for all data, Redis for caching
- **Docker Ready**: One-command deployment

## Quick Start

### 1. Clone and Configure

```bash
git clone <repository-url>
cd crypto-news-bot
cp .env.example .env
```

### 2. Edit `.env` file

Required variables:
- `TELEGRAM_BOT_TOKEN`: Your bot token from @BotFather
- `TELEGRAM_CHANNEL_ID`: Your channel ID (e.g., -1001234567890)
- `ADMIN_ID`: Your Telegram user ID
- `ENCRYPTION_KEY`: Random 32-character string
- AI API keys (at least one provider)

### 3. Deploy with Docker

```bash
docker compose up -d --build
```

### 4. Check logs

```bash
docker compose logs -f bot
```

## Architecture

```
app/
├── core/           # Configuration, database session
├── ai/             # AI providers and services
├── telegram/       # Bot handlers, keyboards, middlewares
├── rss/            # RSS collection
├── news/           # News processing
├── scheduler/      # APScheduler jobs
└── main.py         # Entry point
```

## Admin Commands

All commands accessible via Telegram:

- `/start` - Start bot
- `/stats` - View statistics
- `/sources` - Manage RSS sources
- `/ai` - AI settings (provider, model)
- `/prompts` - Edit AI prompts
- `/digest` - Configure daily digest
- `/system` - System monitoring

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| TELEGRAM_BOT_TOKEN | Bot token | Required |
| TELEGRAM_CHANNEL_ID | Channel ID | Required |
| ADMIN_ID | Admin user ID | Required |
| DATABASE_URL | PostgreSQL URL | postgresql+asyncpg://... |
| REDIS_URL | Redis URL | redis://redis:6379/0 |
| AI_PROVIDER | Primary AI provider | openrouter |
| AI_MODEL | Default model | meta-llama/llama-3-70b-instruct |
| DIGEST_TIME | Daily digest time | 23:59 |
| IMPORTANCE_THRESHOLD | Min score to publish | 50 |

## AI Providers

Supported providers (in fallback order):
1. OpenRouter
2. Groq
3. Google Gemini
4. Anthropic Claude
5. OpenAI
6. Local Ollama

## License

MIT
