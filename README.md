# Matchbook Trading Bot

An automated sports trading bot for Matchbook, featuring a multi-strategy engine, real-time web dashboard, and Telegram notifications.

## Overview

This project is a containerized trading bot designed to interact with the Matchbook Exchange API. It allows users to run multiple independent betting strategies simultaneously, monitor performance through a web-based dashboard, and receive instant alerts via Telegram.

## Key Features

- **Multi-Strategy Engine**: Run multiple strategies side-by-side. Each strategy operates independently with its own configuration, staking plan, and state management.
- **Web Dashboard**: A real-time Flask-based dashboard (accessible on port 8050) to monitor open positions, strategy performance, and historical data.
- **Dynamic Strategy Management**: Add, edit, or remove strategies through the web interface without restarting the entire system (the bot can be restarted individually from the dashboard).
- **Comprehensive Analytics**: Visualizations for profit over time, win rates by odds/league, and market distribution.
- **Telegram Integration**: Instant notifications for successful logins, order placements, and bet settlements.
- **State Persistence**: Each strategy's state (current step in staking plan, active bets) is persisted to JSON files, ensuring continuity across restarts.
- **Dockerized Deployment**: Simple setup and execution using Docker and Docker Compose.

## Prerequisites

- **Matchbook Account**: An active account with Matchbook and API access.
- **Docker & Docker Compose**: Installed on your host machine.
- **Telegram Bot (Optional)**: For receiving alerts.

## Setup Instructions

### 1. Environment Variables

Create a `.env` file in the root directory and provide your credentials:

```env
MATCHBOOK_USERNAME=your_username
MATCHBOOK_PASSWORD=your_password

# Optional: Telegram Alerts
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Optional: Dashboard Password
DASHBOARD_PASSWORD=your_secret_password
```

### 2. Deployment

The project uses Docker Compose to manage the trading bot and the dashboard.

```bash
# Build and start the containers
docker-compose up -d --build
```

This will start two services:
- `matchbook_trading_bot`: The core engine running the strategies.
- `matchbook_dashboard`: The web interface available at `http://localhost:8050`.

## Project Structure

- `src/`: Core Python source code.
  - `main.py`: Entry point for the trading bot.
  - `dashboard.py`: Flask application for the web interface.
  - `api_client.py`: Matchbook API client implementation.
  - `strategy_runner.py`: Logic for executing individual strategies.
  - `market_*.py`: Matchers for different market types (Match Odds, Total, Double Chance, etc.).
- `config/`: Configuration and state files.
  - `strategies.json`: Definitions of all trading strategies.
  - `bets.db`: SQLite database for permanent bet records.
  - `state/`: Directory containing JSON files for strategy progress.
- `logs/`: Bot and application logs.

## Strategies Configuration

Strategies are defined in `config/strategies.json`. Each strategy includes:
- **Sport & Market**: e.g., Soccer Match Odds, Tennis Moneyline.
- **Staking Plan**: Fixed stake or a ladder (Martingale-style).
- **Odds Range**: Minimum and maximum decimal odds.
- **Compound Staking**: Support for all-in/compounding strategies.
- **Filtering**: Exclude specific leagues or set timing (Pre-match/Live).

## Disclaimer

This bot is for educational and personal use. Trading on betting exchanges involves risk. Use at your own discretion.
