"""Commits and pushes your code to GitHub. Run it like this:

    python3 github.py "your commit message"

Skips .env, bets.db, state files, and logs automatically (see .gitignore).
"""

import subprocess
import sys


def run(cmd, allow_fail_text=None):
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    print(result.stdout.strip())
    if result.returncode != 0:
        if allow_fail_text and allow_fail_text in result.stdout:
            return
        print(result.stderr.strip())
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python3 github.py "your commit message"')
        sys.exit(1)

    message = sys.argv[1]

    run("git add .")
    run(f'git commit -m "{message}"', allow_fail_text="nothing to commit")
    run("git push")
    print("Done. Pushed to GitHub.")
