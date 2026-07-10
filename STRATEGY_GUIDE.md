# 📘 Matchbook Trading Bot: Step-by-Step Strategy Guide

Welcome to the **Strategy Management Interface**! This guide is written specifically for beginners (dummies) to help you create, configure, and manage your trading strategies with zero coding required.

By using the web-based Strategy Management Interface, you can define exactly what sports, markets, and odds ranges the bot should scan, how much money to bet, what staking system to use (e.g., Martingale vs. All-In Compounding), and when to cash out.

---

## 🚀 Step 1: Accessing the Strategy Management Interface

1. Open your web browser (Chrome, Edge, Safari, Firefox, etc.).
2. In the address bar, type the following URL and press Enter:
   ```
   http://localhost:8050
   ```
   *(Note: If your bot is hosted on a remote server, replace `localhost` with your server's IP address. If a `DASHBOARD_PASSWORD` was set in your `.env` file, you will be prompted for a username and password. You can leave the username blank or enter anything, and type your dashboard password in the password field.)*
3. Once on the main dashboard page, click the orange **`⚙ Manage Strategies`** button in the top right corner. This will take you directly to:
   ```
   http://localhost:8050/strategies
   ```

---

## 🛠️ Step 2: Choosing Your Strategy Mode

On the **Manage Strategies** page, you will see a list of any existing strategies and two large dashed buttons at the bottom:
* **`+ Add strategy (single sport)`**: Use this if you want your strategy to target exactly one sport and one market (e.g., only backing Soccer Match Odds, or only backing Tennis Match Winner).
* **`+ Add strategy (multi-sport)`**: Use this if you want one strategy to run across multiple sports or different markets at the same time (e.g., a "Multi" strategy that places bets on both Soccer Match Odds and Tennis Moneyline).

Click the button that fits your needs to open the creation modal (the pop-up form).

---

## 📝 Step 3: Filling Out the Strategy Fields (The "Dummy-Proof" Breakdown)

Below is an explanation of every single field you will see in the form, written in plain English.

### 📌 Basic Details
* **Name**: A unique name for your strategy (e.g., `My First Martingale`).
  > ⚠️ **Rule:** Every strategy must have a different name. Do not reuse an existing name!
* **Sport (Single Sport mode only)**: The sport name exactly as offered on Matchbook (e.g., `Soccer`, `Tennis`, `Basketball`, `Ice Hockey`, `Baseball`).
* **Market (Single Sport mode only)**: The target market name exactly as offered on Matchbook (e.g., `Match Odds`, `Moneyline`, `Total`).
* **Bet Side**:
  * `Back the matched selection`: Bet that an event/outcome **will** happen (most common).
  * `Lay the opponent`: Bet that an event/outcome **will not** happen.
  * > ⚠️ **Rule:** Lay-side betting is currently only supported on **Match Odds** and **Moneyline** markets. It cannot be used with cash-out features.
* **Bet Mode**:
  * `Normal`: Bet directly on the market you matched.
  * `Double Chance`: Select this if you want the "Match Odds" market to trigger a bet, but you want the bot to actually place the bet on the **Double Chance** market instead.
  * > ⚠️ **Rule:** Double Chance mode is only supported when backing (Bet Side: Back) and when the triggering Market is set to **Match Odds**.

### 📈 Odds & Total Line Controls
* **Min Back Odds**: The lowest odds you are willing to accept (e.g., `1.45`). The bot will not place a bet if the odds are lower than this.
* **Max Back Odds**: The highest odds you are willing to accept (e.g., `1.60`). The bot will not place a bet if the odds are higher than this.
  > ⚠️ **Rule:** `Min Back Odds` must be less than or equal to `Max Back Odds`.
* **Total Line (Total Market only)**: The line for over/under goals or points (e.g., `2.5` or `1.5`).
* **Direction (Total Market only)**: Choose `Over` or `Under` from the drop-down.
  > ⚠️ **Rule:** If your Market is set to **Total**, both the Total Line and Direction are **required**. If your Market is NOT set to Total, these two fields must be left blank.

### 💰 Money & Staking Controls
* **Strategy Type**:
  * **Normal (staking plan)**: Uses a list of specific bet amounts (steps). If a bet loses, the bot moves to the next step in your list on the next match. If a bet wins, the bot resets to the first step.
  * **Compound (all-in, compounding)**: Starts with a small amount and rolls the entire balance (stake + winnings) into the next bet, compounding your money until a target is reached.
* **Staking Plan (Normal Type only)**: A comma-separated list of bet amounts (e.g., `0.1, 0.3, 0.9, 2.7, 8.1, 24.3`). This is how much the bot will bet at each step.
* **Starting Balance (Compound Type only)**: The starting stake for your compound chain (e.g., `10`).
* **Target Amount (Compound Type only)**: The goal balance where the compound chain wins and resets (e.g., `20`). Must be greater than the starting balance.
* **Bankroll**: The total money allocated to this strategy (e.g., `100`).
* **Max Session Loss**: If the strategy loses this amount of money during its current run, it will automatically disable itself to protect your funds.
* **Target Profit**: If the strategy makes this amount of profit, it will stop and disable itself.
* **Max Open Bets**: The maximum number of bets this strategy can have pending at the same time (usually `1` to avoid overlapping risk).

### ⏱️ Timing & Bot Behavior
* **Poll Interval (seconds)**: How often the bot scans Matchbook for new matches (e.g., `600` for every 10 minutes, or `30` for every 30 seconds if you are betting live).
* **Cooldown after bet (seconds)**: How long the bot waits after placing a bet before it scans for another one (e.g., `600` seconds).
* **Lookahead (minutes)**: How far into the future the bot should search for upcoming matches (e.g., `180` minutes to look 3 hours ahead).
* **Min seconds to start**: The minimum amount of time remaining before a match starts for the bot to place a pre-match bet (e.g., `300` seconds / 5 minutes). This prevents placing a pre-match bet at the very last second.
* **Minimum Liquidity**: The minimum amount of money (in your currency) that must be available in the Matchbook betting pool for the runner. This ensures your bet gets matched instantly (e.g., `2` or `5`).
* **Cash Out at % of stake**: Automatic profit/loss target to exit a bet early.
  > ⚠️ **Rule:** Cash-out is **only** supported for single-step strategies (a staking plan with only one number, like `0.5`). It is not supported for multi-step staking plans or lay-side bets.
* **Betting Timing**:
  * `Pre-match only`: Only bet before the match starts.
  * `Live only`: Only bet while the match is actively in-play.
  * `Both`: Bet pre-match or live.

---

## 🚫 Step 4: Selecting Excluded Leagues

If there are specific leagues you want to avoid (for example, lower-tier leagues or leagues with unpredictable results):
1. Scroll down to the **Exclude Leagues** box.
2. You will see a list of leagues that the bot has previously discovered.
3. Check the box next to any league you want this strategy to **ignore**.
4. The bot will automatically skip any matches belonging to those checked leagues.

---

## 💾 Step 5: Saving and Activating Your Strategy

1. Double-check all of your inputs.
2. Click the orange **`Save`** button at the bottom of the modal.
3. The modal will close, and your new strategy will appear in the main list.
4. By default, new strategies are enabled (Active). If you want to temporarily pause it, click the **`Disable`** button next to its name on the main page.
5. If you make a mistake, click the **`Edit`** button to modify your settings.

---

## 🔄 Step 6: Restarting the Bot (The Most Important Step!)

When you add, edit, or remove a strategy via the interface, the changes are saved to the configuration file immediately, but **the running bot container does not know about them yet**.

To apply your changes to the live bot:
1. Look at the top right of the **Manage Strategies** page.
2. Click the yellow **`⟲ Restart Bot`** button.
3. A message saying "Restarting the bot..." will appear.
4. Once completed, a pop-up confirmation will say "Bot restarted."
5. The trading bot has now restarted, re-read the configuration, and is running your new strategy!

---

## 💡 Pro-Tips & Troubleshooting

* **My Strategy isn't placing bets?**
  * Check the main dashboard to see if there are any active positions.
  * Ensure the bot is running and that your account has enough balance.
  * Ensure the odds of the available matches fall exactly within your `Min Back Odds` and `Max Back Odds` range.
  * Check if the sport name is active on Matchbook today. If Matchbook isn't offering that sport right now, the bot will print a warning log and temporarily skip the strategy until it's available.
* **How do I reset my staking steps back to Step 1?**
  * If a multi-step strategy gets deep into its staking plan (e.g., Step 4 or 5) and you want to manually force it back to Step 1 without losing your historical stats, click the **`Reset State`** button next to the strategy's name on the Manage Strategies page, then click **`⟲ Restart Bot`**.
* **How do I delete a strategy?**
  * Simply click the red **`Remove`** button next to the strategy you want to delete. Remember to click **`⟲ Restart Bot`** afterwards to apply the deletion!
