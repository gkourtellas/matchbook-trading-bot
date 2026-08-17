#!/usr/bin/env python3
"""Restart the Matchbook trading bot (Docker Compose)."""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


def run(cmd):
    print(f"\n> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_DIR)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main():
    print(f"Project folder: {PROJECT_DIR}")
    run(["docker", "compose", "down"])
    run(["docker", "compose", "up", "-d", "--build"])
    print("\nBot restarted. Log file (after it runs): logs/bot.log")
    print("Watch live output: docker compose logs -f trading-bot")


if __name__ == "__main__":
    main()
