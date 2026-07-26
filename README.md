# Crypto News AI Bot

Production-ready Telegram bot for crypto news collection, AI analysis, and publishing.

## Features

- Collects news from multiple RSS sources
- Analyzes news with AI (DashScope Qwen models)
- Publishes important news to Telegram channel
- Daily digest of news
- Admin panel for configuration
- Multi-language support

## Architecture

5 logical modules in one repository:

| Module | Description |
|--------|-------------|
| **Core & Infrastructure** | Config, database, logging, repositories |
| **News Collector** | RSS parser, API scrapers, news processor |
| **AI Service** | DashScope Qwen integration, analysis, digest |
| **Telegram Bot** | Handlers, filters, middleware, publisher, admin panel |
| **Scheduler** | APScheduler jobs for collection and daily digest |

## Quick Start (Local Development)

```bash
# 1. Create virtual environment
cd crypto-news-bot
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure .env
cp .env.example .env
# Edit .env with your bot token and settings

# 4. Run the bot
python -m src.main
```

## Docker Deployment

```bash
docker-compose up -d
```

## Deployment

### Railway Deployment

See [DEPLOY_RAILWAY.md](DEPLOY_RAILWAY.md) for Railway deployment instructions.

### GitHub Repository

See [GITHUB_SETUP.md](GITHUB_SETUP.md) for GitHub repository setup instructions.

## Admin Panel

Send `/admin` to the bot to access the admin panel.

## Environment Variables

See `.env.example` for all available settings.
