# Matchbook Trading Bot

Automated betting strategy for the [Matchbook](https://www.matchbook.com/) exchange. The bot scans pre-match football markets, places back bets when odds fall in a configured band, tracks settlement, and advances a six-step progression ladder. Optional Telegram notifications report logins, bets, and results.

## Architecture

```
strategy_one.py  →  MatchbookClient (api_client.py)  →  Matchbook REST API
                    └→ Telegram Bot API (optional)
```

- **`src/strategy_one.py`** — Main loop: market scan, trigger logic, wait period, settlement polling, step management.
- **`src/api_client.py`** — Session auth, events, orders, and Telegram helper.

## Prerequisites

- Active Matchbook account with API access
- [Docker](https://docs.docker.com/get-docker/) **or** Python 3.11+
- (Optional) Telegram bot and chat ID for alerts

## Quick start

1. Clone the repository and go to the project root.

2. Create your environment file:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your credentials. Never commit `.env` to version control.

3. Run with Docker (recommended):

   ```bash
   docker compose up --build
   ```

   Or run locally:

   ```bash
   pip install -r requirements.txt
   cd src
   python strategy_one.py
   ```

## Runtime behavior (current code)

Loaded from `config/settings.json` at startup (`mode`, odds band, per-step stakes, `max_steps`).

| Setting | Value |
|---------|-------|
| Sport ID | `15` (football) |
| Market | Match Odds |
| Odds band | `odds_min` – `odds_max` in settings |
| Stake | Per step from `stakes.testing` or `stakes.production` |
| Max steps | `max_steps` in settings |
| Scan interval | 15 seconds |
| Post-bet hold | 110 minutes after kickoff |

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for environment variables and the settings file schema.

## Project progress

Track backlog, standups, and what is done in **[docs/PROJECT_TRACKER.md](docs/PROJECT_TRACKER.md)**.

## Documentation

| Guide | Description |
|-------|-------------|
| [docs/PROJECT_TRACKER.md](docs/PROJECT_TRACKER.md) | Backlog, standup log, done history |
| [docs/STRATEGY.md](docs/STRATEGY.md) | Strategy logic, filters, settlement, step ladder |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Environment variables and `settings.json` |
| [docs/COMMANDS.md](docs/COMMANDS.md) | Docker build, restart, logs, quick reference |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker and local deployment |
| [docs/API.md](docs/API.md) | `MatchbookClient` and API endpoints used |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common issues and fixes |

## Security

- **Do not commit** `.env` or real credentials. Use `.env.example` as a template only.
- If credentials were ever pushed to a remote repository, **rotate** your Matchbook password and regenerate your Telegram bot token immediately.
- Review [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md#secrets-exposed-in-git) for recovery steps.

## Disclaimer

This software is for educational and personal use. It is **not** financial advice. Exchange betting involves real financial risk. You are responsible for compliance with Matchbook’s terms of service and applicable laws in your jurisdiction. Test with small stakes and understand the strategy before running in production.

## Project layout

```
├── README.md
├── .env.example
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── config/settings.json
├── docs/
└── src/
    ├── api_client.py
    └── strategy_one.py
```
