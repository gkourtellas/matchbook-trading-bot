# Configuration

## Environment variables

Set these in a `.env` file at the project root (see `.env.example`). Docker Compose loads them via `env_file`.

| Variable | Required | Description |
|----------|----------|-------------|
| `MATCHBOOK_USERNAME` | Yes | Matchbook account username |
| `MATCHBOOK_PASSWORD` | Yes | Matchbook account password |
| `TELEGRAM_BOT_TOKEN` | No | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | No | Chat ID for alert messages |

If `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is missing, `send_telegram()` returns without sending (no error).

### Example setup

```bash
cp .env.example .env
# Edit .env with your values
```

Never commit `.env` to git. It is listed in `.gitignore`.

---

## `config/settings.json`

This file defines **intended** strategy parameters. The Python code does **not** read it yet.

### Schema

```json
{
  "mode": "testing",
  "max_steps": 6,
  "odds_min": 1.45,
  "odds_max": 1.60,
  "stakes": {
    "testing": [0.11, 0.12, 0.13, 0.14, 0.15, 0.16],
    "production": [0.10, 0.30, 0.90, 2.70, 8.10, 24.30]
  }
}
```

| Field | Meaning |
|-------|---------|
| `mode` | `"testing"` or `"production"` — selects which stake array to use (when implemented) |
| `max_steps` | Ladder length (matches hardcoded `6` in code) |
| `odds_min` / `odds_max` | Back-odds trigger band |
| `stakes.testing` | Six stakes for test mode (one per step) |
| `stakes.production` | Six stakes for live mode (progressive sizing) |

### Intended vs actual runtime

| Setting | `settings.json` | Current code (`strategy_one.py`) |
|---------|-----------------|----------------------------------|
| Odds band | 1.45 – 1.60 | 1.45 – 1.60 (hardcoded) |
| Max steps | 6 | 6 (hardcoded) |
| Stake | Per-step arrays | Fixed `0.10` |
| Mode | testing / production | Not used |

### Future work

Wire `settings.json` into the strategy loop so `mode`, odds bounds, `max_steps`, and per-step stakes are loaded at startup without code changes.

---

## Other constants (code only)

These are only in `strategy_one.py` and are not in `settings.json`:

| Constant | Value |
|----------|-------|
| `target_sport_id` | `"15"` |
| `loop_interval` | 15 (seconds between scans) |
| Post-bet hold | 110 minutes after kickoff |
| Settlement poll | 60 seconds |
| Wait loop sleep | 30 seconds during hold |

See [STRATEGY.md](STRATEGY.md) for full behavioral detail.
