# Strategy Configuration System

## Overview
The admin console now includes a **Strategy Configuration** panel where you can modify most betting parameters without touching code. Changes are saved to `strategies.json` and automatically restart the bot.

> Note: Advanced risk settings such as `max_total_exposure` and `max_session_loss` are still supported by the bot, but they are not exposed in the current admin UI and must be changed directly in `strategies.json`.

## How to Use

### 1. Access the Strategy Configuration Panel
Open the admin console (`http://monitor:5051/admin`) and scroll down to the **Strategy Configuration** section.

### 2. Available Parameters

**Betting Scope:**
- **Sports (multi-select)**: Select one or more major sports
- **Markets (multi-select)**: Select one or more major markets (1X2, Match Odds, Over/Under, Asian Handicap, etc.)

**Odds & Stakes:**
- **Min Back Odds**: Minimum odds threshold (e.g., 1.45)
- **Max Back Odds**: Maximum odds threshold (e.g., 1.60)
- **Base Stake**: Not used directly; staking plan defines actual stakes
- **Max Open Bets**: Maximum concurrent bets allowed (e.g., 1)

**Staking Plan:**
- **Staking Plan**: Comma-separated multipliers (e.g., `0.1, 0.3, 0.9, 2.7, 8.1, 24.3`)
  - After a WIN, resets to first value (0.1)
  - After a LOSE, advances to next step
  - This is a **martingale-style increasing strategy**

**Risk Management:**
- **Max Total Exposure**: Maximum total money at risk across all open bets
- **Max Session Loss**: Stop trading after losing this amount in a session

> Note: The current admin console does not expose `max_total_exposure` or `max_session_loss`. These advanced risk fields remain configurable directly in `strategies.json`.

**Scanning & Timing:**
- **Poll Interval (seconds)**: How often to scan for betting opportunities (60 = every minute)
- **Pause Scanning With Open Positions**: If enabled, bot slows scan checks while there is already an open bet/offer
- **Open Positions Cooldown Seconds**: Sleep interval used while open positions exist
- **Event Lookahead (minutes)**: How far into the future to look for events (180 = 3 hours)
- **Min Seconds to Start**: Don't bet on events starting sooner than this (300 = 5 minutes)
- **Minimum Liquidity**: Minimum available liquidity required to place a bet

### 2.1 Plain-English Explanations (Requested)

- **Poll interval seconds**: Time between normal scan cycles. Larger value means fewer API calls.
- **Minimum liquidity**: Minimum market depth required before placing a bet, to avoid thin markets.
- **Max total exposure**: Max amount of stake currently at risk across all open positions.
- **Max session loss**: Stop-loss for the session; bot stops when losses hit this amount.

### 2.2 API-Call Reduction Setup

To reduce API usage:
1. Increase **Poll Interval Seconds** (example: 120 or 180).
2. Keep **Pause Scanning With Open Positions** = Yes.
3. Set **Open Positions Cooldown Seconds** higher than poll interval (example: 300).

Recommended conservative profile:
- `poll_interval_seconds: 120`
- `pause_scanning_with_open_positions: true`
- `open_positions_cooldown_seconds: 300`

### 3. Save & Restart
- Click **"Save & Restart Bot"** to apply changes
- The bot will:
  1. Stop gracefully
  2. Save the new configuration to `strategies.json`
  3. Reload and restart with new parameters
- Status banner shows progress

### 4. Discard Changes
- Click **"Discard Changes"** to revert unsaved form values to last saved configuration

### 5. Reset Staking Plan To Start Over

If you are mid-plan (for example step 3) and want to restart from step 1:
1. Click **Reset Plan To Step 1** in the Strategy panel.
2. The admin API resets `staking_step_index` to `0` in `state.json`.
3. Bot automatically restarts.
4. Next bet starts from the first staking plan value.

## Configuration File

All strategy configurations are stored in:
```
strategies.json
```

Example structure:
```json
{
  "strategies": [
    {
      "name": "Default Football",
      "description": "Primary Football Match Odds strategy with martingale staking",
      "enabled": true,
      "sport_name": "Football",
      "market_name": "Match Odds",
      "min_back_odds": 1.45,
      "max_back_odds": 1.60,
      "base_stake": 0.1,
      "staking_plan": [0.1, 0.3, 0.9, 2.7, 8.1, 24.3],
      "max_open_bets": 1,
      "max_total_exposure": 10.0,
      "max_session_loss": 10.0,
      "target_profit": 20.0,
      "bankroll": 1000.0,
      "poll_interval_seconds": 60,
      "pause_scanning_with_open_positions": true,
      "open_positions_cooldown_seconds": 300,
      "event_lookahead_minutes": 180,
      "min_seconds_to_start": 300,
      "odds_type": "DECIMAL",
      "currency": "GBP",
      "minimum_liquidity": 2.0,
      "keep_in_play": false
    }
  ]
}
```

## Technical Details

- `target_profit`: stop the strategy when the strategy-level session profit reaches this value.
- `max_session_loss`: stop the strategy when the strategy-level session loss reaches this value.
- On either stop condition, the bot sends a Telegram notification and ends that strategy run.

### How Bot Loads Configuration
1. Bot starts → calls `load_enabled_strategy_configs()`
2. Function reads `strategies.json`
3. Loads all strategies with `"enabled": true`
4. Creates `LiveBotConfig` objects from those strategy parameters
5. Falls back to legacy `live_config.example.json` if `strategies.json` is missing

### How Configuration Is Saved
1. User fills form in admin console
2. Click "Save & Restart Bot"
3. POST request to `/api/config` with new parameters
4. Admin app saves to `strategies.json`
5. Admin app calls bot restart (`/api/admin/restart`)
6. Bot exits gracefully
7. Admin starts new bot process, which loads new config

### API Endpoints

**GET /api/config**
- Returns all strategies in `strategies.json`
- Example: `{"strategies": [{...}]}`

**POST /api/config**
- Updates a strategy by name
- Auto-restarts bot if `autoRestart: true`
- Payload: `{"name": "Default Football", "min_back_odds": 1.50, ..., "autoRestart": true}`

## Future Enhancements

- [ ] Support multiple **simultaneous strategies** (one bot per strategy)
- [ ] Add strategy **templates** ("Aggressive", "Conservative", "Scalper")
- [ ] Strategy **cloning** / **duplication** in UI
- [ ] Validation rules in form (e.g., min_odds < max_odds)
- [ ] Live preview of "next step stake" based on staking plan
- [ ] Historical strategy performance tracking

## Troubleshooting

**Form doesn't load:**
- Check browser console for errors
- Verify token is saved (paste it in Token field)
- Check `/admin/logs` for server errors

**Changes don't apply:**
- Wait 3-5 seconds after clicking Save, bot may take time to restart
- Check if bot status changes from RUNNING → STOPPED → RUNNING
- Look at logs to confirm bot loaded new config

**Bot crashes after saving:**
- Check log file for reason
- Values may be out of acceptable range
- Staking plan should be comma-separated numbers (e.g., "0.1, 0.3, 0.9")

## Key Variables Made Configurable

Previously hardcoded, now adjustable from UI:
- ✅ Market (`market_name`)
- ✅ Odds range (`min_back_odds`, `max_back_odds`)
- ✅ Base stake amount (`base_stake`)
- ✅ Staking plan strategy (`staking_plan` array)
- ✅ Sport selection (`sport_name`)
- ✅ Number of steps / plan length (implicit in `staking_plan` length)
- ✅ Fixed vs increasing strategy (hardcoded as increasing; changeable via plan edit)
- ✅ Risk limits (`max_total_exposure`, `max_session_loss`)
- ✅ Scan frequency (`poll_interval_seconds`)
- ✅ Event timing parameters


