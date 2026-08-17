# Useful commands

Run these from the **project root** (where `docker-compose.yml` lives), unless noted.

Container name: `matchbook_trading_bot`  
Compose service: `trading-bot`

---

## Docker — build and run

### Build and start (foreground, see logs in terminal)

```bash
docker compose up --build
```

```powershell
docker compose up --build
```

### Build only (no start)

```bash
docker compose build
```

### Start without rebuild (image already built)

```bash
docker compose up
```

### Start in background (detached)

```bash
docker compose up -d --build
```

Stop watching with `Ctrl+C` only applies to foreground mode. For detached, use [stop](#stop) below.

### Rebuild from scratch (after Dockerfile or requirements change)

```bash
docker compose build --no-cache
docker compose up -d
```

---

## Restart

Compose uses `restart: "no"`, so the container does **not** auto-restart when the process exits. Use one of these:

### Quick restart (same image, reload `.env` on recreate)

```bash
docker compose restart
```

### Full restart (recommended after `.env` or compose changes)

```bash
docker compose down
docker compose up -d --build
```

Or from the project folder:

```bash
python restart.py
```

### Save and upload to GitHub

```bash
python github.py "describe your changes"
```

Does not allow committing `.env`.

### Restart only the bot container by name

```bash
docker restart matchbook_trading_bot
```

---

## Logs

### Log file in project (for review / Cursor)

All `print` output is copied to:

**`logs/bot.log`** (in the project folder, next to `docker-compose.yml`)

Rotates at 10 MB, keeps 3 old files (`bot.log.1`, etc.).

Tail on the server:

```bash
tail -f logs/bot.log
```

Restart after this feature was added:

```bash
docker compose down
docker compose up -d --build
```

### Follow live logs (foreground attach)

```bash
docker compose logs -f
```

### Follow logs for the trading service only

```bash
docker compose logs -f trading-bot
```

### Last 100 lines, then follow

```bash
docker compose logs -f --tail=100 trading-bot
```

### Logs without following (snapshot)

```bash
docker compose logs --tail=200 trading-bot
```

### Docker CLI by container name

```bash
docker logs -f matchbook_trading_bot
```

---

## Stop and status

### Stop containers (keeps them; can `up` again)

```bash
docker compose stop
```

### Stop and remove containers/networks

```bash
docker compose down
```

### Is the bot running?

```bash
docker compose ps
```

```bash
docker ps -a --filter name=matchbook_trading_bot
```

---

## Shell and debugging

### Open a shell inside the running container

```bash
docker compose exec trading-bot bash
```

If `bash` is missing:

```bash
docker compose exec trading-bot sh
```

### Run strategy once manually inside container

```bash
docker compose exec trading-bot python -u src/strategy_one.py
```

### Inspect environment (names only — do not paste output with secrets)

```bash
docker compose exec trading-bot env | findstr MATCHBOOK
```

PowerShell:

```powershell
docker compose exec trading-bot env | Select-String MATCHBOOK
```

---

## Local run (no Docker)

From project root:

```bash
pip install -r requirements.txt
cd src
python strategy_one.py
```

PowerShell from project root:

```powershell
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python src/strategy_one.py
```

Ensure `.env` variables are loaded in your shell, or use Docker so Compose loads `.env` automatically.

---

## Git hygiene (credentials)

```bash
git check-ignore -v .env
git status
```

If `.env` is tracked:

```bash
git rm --cached .env
```

---

## Quick reference

| Task | Command |
|------|---------|
| Build + run (see output) | `docker compose up --build` |
| Run in background | `docker compose up -d --build` |
| Restart | `docker compose down && docker compose up -d` |
| Live logs | `docker compose logs -f trading-bot` |
| Stop | `docker compose stop` |
| Remove | `docker compose down` |
| Status | `docker compose ps` |
| Shell in container | `docker compose exec trading-bot bash` |

---

## Related docs

- [DEPLOYMENT.md](DEPLOYMENT.md) — setup and volume behavior
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — when commands fail
- [CONFIGURATION.md](CONFIGURATION.md) — `.env` variables
