# User Guide: Matchbook Trading Bot Dashboard

Welcome to the Matchbook Trading Bot. This guide will help you navigate the dashboard and manage your automated trading strategies.

## Accessing the Dashboard

Once the system is running, open your web browser and go to:
`http://localhost:8050`

If you set a `DASHBOARD_PASSWORD` in your `.env` file, you will be prompted for a username (you can leave it blank) and the password.

## 1. Live Dashboard (Home)

The main page provides a real-time overview of your bot's activity:

- **Open Positions**: Shows bets that have been placed but are not yet settled.
- **Strategy Performance**: A summary table of all strategies (active and inactive), showing total bets, win rate, and total profit.
- **Profit Charts**: Visual representation of your earnings over daily, monthly, and yearly periods.
- **Recent Bets**: A detailed list of the last 50 settled bets.

## 2. Managing Strategies

Click the **"⚙ Manage Strategies"** button at the top of the dashboard to view and edit your strategies.

### Adding a Strategy
- **Add strategy (single sport)**: Create a strategy that targets one specific sport and market.
- **Add strategy (multi-sport)**: Create a strategy that can scan multiple sports and markets simultaneously using a shared staking plan.

### Editing a Strategy
Click **"Edit"** on any existing strategy to modify its parameters:
- **Bet Side**: Choose "Back" to bet on the selection or "Lay" to bet against it (available for Match Odds/Moneyline).
- **Staking Plan**: Enter a comma-separated list of stakes (e.g., `0.1, 0.3, 0.9`). The bot will move to the next step after a loss and reset to the first step after a win.
- **Compound Type**: Switch to "Compound" for all-in strategies where you set a starting balance and a target.
- **Live Mode**: Choose whether to scan "Pre-match only", "Live only", or "Both".
- **Cash Out**: Set a target profit percentage (e.g., `5`) to automatically lock in profit during a match if odds move in your favor.

### Applying Changes
After saving or deleting a strategy, you **must** click the **"⟲ Restart Bot"** button at the top of the "Manage Strategies" page. This tells the trading engine to reload the configuration and apply your changes.

## 3. Analytics

Click **"Analytics →"** on the main dashboard to dive deeper into your performance data:

- **Cumulative Profit**: A line chart showing your overall growth.
- **Win Rate by Odds**: See which odds ranges are most profitable for your strategies.
- **Market Mix**: A breakdown of bet volume per strategy.
- **Profit per League**: Identify which competitions are performing best (and worst).

## Troubleshooting Tips

- **Bot not placing bets?**
  - Check the "Enabled" badge on the Manage Strategies page.
  - Verify that your Matchbook account has sufficient balance.
  - Ensure the odds of available matches fall within your strategy's Min/Max odds range.
  - Check the bot logs (`logs/bot.log`) for any specific error messages.
- **Restarting**: If the dashboard feels out of sync or you've made major config changes, use the "Restart Bot" button.

---
*Note: Always monitor your active strategies and bankroll. Automated trading should be used responsibly.*
