# Project tracker

Living backlog and standup log for the Matchbook trading bot. Update this when you start or finish work, or at the end of a session.

**Quick standup (copy for chat or notes):**

```
Yesterday / last session: …
Today / focus: …
Blockers: …
```

---

## Current snapshot

*Last updated: 2026-05-31*

| | |
|---|---|
| **Done recently** | Docs + repo hygiene; project tracker; settlement wait (110 min + poll until settled) before resuming scans |
| **In progress** | — |
| **Up next** | Verify settle fix in prod; Athens time in all logs (see [Fixes](#fixes)) |
| **Blocked** | — |

---

## Fixes

Bugs or incorrect behavior to correct. Check off when verified in production.

### Step ladder (incremental logic)

- [x] **Win → step 1; loss → +1** — only after Matchbook outcome (no event-list guess)
- [ ] **Verify in production** — fixed: correct offers API URL, settled-bets report, no “assume win”

### Telegram — settlement notifications

- [x] **Won / Lost** on settlement message (no offer ID in Telegram)
- [ ] **Verify in production** — message only sends when Matchbook returns settled P/L

### Time display (Athens)

- [ ] **All logs and messages use Athens time** — format `HH:MM` or `HH:MM:SS` everywhere
- [ ] **Fix scan logs** — scanning line currently UTC (`time.strftime` on local/UTC); should match Athens (+3) like bet/settle messages

---

## Backlog

Other prioritized work (not the fixes above). Move to [Done log](#done-log) when shipped.

### High priority

- [x] **Load `config/settings.json` in code** — `mode`, odds bounds, `max_steps`, per-step stakes from `stakes.testing` / `stakes.production`
- [x] **Use step index for stake** — stake from config for `current_step`
- [ ] **Confirm `.env` is not tracked** — if it was ever committed, rotate credentials and `git rm --cached .env` (see [TROUBLESHOOTING.md](TROUBLESHOOTING.md#secrets-exposed-in-git))

### Medium priority

- [ ] **401 retry on strategy event fetches** — use `MatchbookClient` or shared retry instead of raw `requests.get` without re-auth
- [ ] **Docker smoke test** — `docker compose up --build` on a machine with Docker installed
- [ ] **Persist `current_step` across restarts** — file or small state store so a crash does not reset the ladder

### Low priority / ideas

- [ ] Use `get_live_events()` instead of duplicating `/events` params in `strategy_one.py`
- [ ] Structured logging (JSON or log file) for post-mortems
- [ ] Health check endpoint or heartbeat if running under orchestration
- [ ] Unit tests for step ladder logic and odds filter

---

## Future roadmap

Larger features — not scheduled for immediate sprint.

| # | Item | Notes |
|---|------|--------|
| 1 | **Database for reports** | Store bets, settlements, P/L, step history for reporting and analysis |
| 2 | **List of leagues** | Configurable allow/deny or target list of competitions (e.g. from `meta-tags` / COMPETITION) |
| 3 | **Dashboard** | Monitor bot status, basic commands (start/stop/pause), add or modify strategies without editing code |

---

## Done log

Reverse chronological — what shipped and when.

| Date | Item |
|------|------|
| 2026-05-31 | Project tracker; backlog for fixes + future roadmap |
| 2026-05-31 | Documentation set: `README.md`, `docs/STRATEGY`, `CONFIGURATION`, `DEPLOYMENT`, `API`, `TROUBLESHOOTING` |
| 2026-05-31 | Repo hygiene: `.gitignore`, `.env.example`, `requirements.txt`, repaired `Dockerfile` |
| 2026-05-31 | Module docstrings in `api_client.py`, `strategy_one.py` |
| *(earlier)* | Settlement wait: pause scanning until bet settled (110 min + polling) |
| *(earlier)* | Core bot: `MatchbookClient`, `strategy_one.py`, Docker Compose, `config/settings.json` (schema only) |

---

## Daily standup log

Newest entry at the top. Add a block when you work on the project (even solo).

### 2026-05-31 (update)

**Yesterday / last session:** Documentation and repo hygiene.

**Today / focus:** Tracker updated with fixes (step ladder, Telegram settlement) and future items (DB, leagues, dashboard).

**Blockers:** None.

**Notes:** Step ladder fix still open. Settlement Telegram needs simple Won/Lost only — not seen in practice yet.

---

### 2026-05-31

**Yesterday / last session:** Initial bot and Docker setup; strategy loop with hardcoded params.

**Today / focus:** Documentation and repo hygiene completed. Tracker file added for ongoing work.

**Blockers:** None. Docker build not verified on dev machine (Docker not in PATH here).

**Notes:** `settings.json` still not wired.

---

### Template (copy for next day)

```markdown
### YYYY-MM-DD

**Yesterday / last session:**

**Today / focus:**

**Blockers:**

**Notes:**
```

---

## How to use this file

1. **Start of session** — Read [Current snapshot](#current-snapshot); pick from [Fixes](#fixes) or [Backlog](#backlog).
2. **End of session** — Update snapshot, check off items, add a [Done log](#done-log) row, append a standup entry.
3. **New idea** — Add under [Future roadmap](#future-roadmap) or Backlog (Low priority).
4. **Blocked** — Put it in snapshot **Blocked** and mention in the standup log.

Technical behavior: [STRATEGY.md](STRATEGY.md), [CONFIGURATION.md](CONFIGURATION.md).
