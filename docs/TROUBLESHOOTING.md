# Troubleshooting

## Authentication and session

### Login fails on startup

**Symptoms:** `Initial authentication failed.` or Telegram login failure message.

**Checks:**

- `MATCHBOOK_USERNAME` and `MATCHBOOK_PASSWORD` in `.env` are correct
- No extra spaces or quotes around values in `.env`
- Matchbook account is active and not locked
- Network can reach `api.matchbook.com`

### 401 errors mid-run

**Symptoms:** Empty event data, failed orders after running for a while.

**Cause:** Session token expired.

**Behavior:** `MatchbookClient` methods retry once after `login()`. Direct `requests.get` calls in `strategy_one.py` do **not** auto-refresh the session.

**Fix:** Restart the bot, or refactor event fetches to use client methods with 401 retry.

---

## Orders

### Order submission rejected

**Symptoms:** `Execution routing declined` or log: `Order submission rejected. Status: ...`

**Checks:**

- Sufficient account balance for stake `0.10`
- Market still open and selection valid
- Odds still available at submitted price
- Matchbook minimum stake and market rules

Read the printed HTTP status and response body from `submit_order()`.

### Bets never placed

**Symptoms:** Scan loop runs but no triggers.

**Checks:**

- Selection best **back** must be between **1.45** and **1.60**
- Event must be **pre-match** (not in-play; kickoff in the future)
- Market name must be exactly **Match Odds**
- Sport ID `15` events must exist in the API response
- Another bet may be in progress (scanning pauses until settlement)

---

## Telegram

### No notifications

**Symptoms:** Bot runs but no Telegram messages.

**Checks:**

- Both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set in `.env`
- Bot has been started in Telegram (`/start` with your bot)
- Chat ID is correct (user ID or group ID)
- Container/process has updated env after editing `.env` (restart required)

**Note:** Missing Telegram config fails **silently** by design.

### Login messages only

Telegram is sent on login, bet, and settlement. If you only see login messages, the strategy may not be finding qualifying markets or orders may be failing.

---

## Docker

### Build fails

**Symptoms:** `docker build` errors on `Dockerfile`.

**Checks:**

- `Dockerfile` is a single valid image definition (no duplicated `FROM` blocks)
- `requirements.txt` exists at project root
- Docker has network access to pull `python:3.11-slim` and pip packages

### Container exits immediately

**Checks:**

- View logs: `docker compose logs`
- Login failure causes early `return` from `main()`
- `restart: "no"` — container stays stopped after exit

### Code changes not applied

With the default volume mount, `src/` is mounted from the host. Restart the container after edits if the process cached imports oddly, or confirm you saved files on the host path mounted into `/app/src`.

---

## Configuration

### `settings.json` has no effect

Expected: the file is **not loaded** yet. Only hardcoded values in `strategy_one.py` apply. See [CONFIGURATION.md](CONFIGURATION.md).

### Wrong stake or odds

Edit `strategy_one.py` (current code) or implement loading from `settings.json` (planned).

---

## Secrets exposed in git

If `.env` or real credentials were committed to a remote repository:

1. **Rotate immediately:** change Matchbook password; revoke and recreate Telegram bot token via [@BotFather](https://t.me/BotFather).
2. Ensure `.env` is in `.gitignore` and not tracked: `git rm --cached .env` if needed.
3. Consider rewriting git history (`git filter-repo` or BFG) if secrets remain in old commits.
4. Never paste real tokens or passwords into issues, docs, or chat logs.

Documentation and `.env.example` use placeholders only.

---

## Getting help

When reporting issues, include:

- Relevant log lines (redact credentials)
- Docker vs local run
- Whether login succeeds
- Sample API response status codes (not passwords)

See also [DEPLOYMENT.md](DEPLOYMENT.md) and [API.md](API.md).
