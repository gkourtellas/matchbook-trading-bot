# Deployment

## Docker (recommended)

### Requirements

- Docker Engine and Docker Compose v2

### Steps

1. Copy and fill environment variables:

   ```bash
   cp .env.example .env
   ```

2. Build and run:

   ```bash
   docker compose up --build
   ```

3. Stop with `Ctrl+C` or:

   ```bash
   docker compose down
   ```

### Compose behavior

From `docker-compose.yml`:

| Setting | Effect |
|---------|--------|
| `build: .` | Builds image from `Dockerfile` |
| `env_file: .env` | Injects credentials into the container |
| `volumes: ./src:/app/src` | Live-mounts source — edit Python without rebuild |
| `restart: "no"` | Container **does not** auto-restart on exit |

If the strategy process exits (error or normal), the container stops until you start it again. This is intentional for manual control.

### Image contents

The `Dockerfile`:

- Base: `python:3.11-slim`
- Installs build deps and `requests` from `requirements.txt`
- Copies `src/` to `/app/src/`
- Runs: `python -u src/strategy_one.py` (unbuffered stdout)

Rebuild after changing `requirements.txt` or `Dockerfile`:

```bash
docker compose build --no-cache
docker compose up
```

---

## Local Python

### Requirements

- Python 3.11+
- pip

### Steps

1. Create `.env` at project root (same variables as Docker).

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run from the `src` directory (imports use `from api_client import ...`):

   ```bash
   cd src
   python strategy_one.py
   ```

   Alternatively from the project root:

   ```bash
   PYTHONPATH=src python src/strategy_one.py
   ```

   On Windows PowerShell:

   ```powershell
   $env:PYTHONPATH="src"
   python src/strategy_one.py
   ```

Environment variables must be visible to the process. Options:

- Export variables in your shell before running
- Use a tool such as `python-dotenv` (not included by default)
- Load `.env` manually in your environment

Docker is simpler because Compose loads `.env` automatically.

---

## Logs

- Docker: logs appear in the terminal attached to `docker compose up`
- Use `docker compose logs -f` if running detached (`-d`)

The strategy prints scan timestamps, triggers, wait periods, and settlement checks to stdout.

---

## Updating code

| Change | Action |
|--------|--------|
| Edit `src/*.py` with volume mount | Restart container or save and let loop continue (no rebuild) |
| Edit `requirements.txt` or `Dockerfile` | `docker compose up --build` |
| Edit `.env` | Restart container |

---

## Related docs

- [COMMANDS.md](COMMANDS.md) — copy-paste commands (build, restart, logs)
- [CONFIGURATION.md](CONFIGURATION.md) — credentials and settings file
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — build and runtime issues
