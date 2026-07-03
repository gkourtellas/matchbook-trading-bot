import subprocess

def run(cmd):
    print(f"> {' '.join(cmd)}")
    r = subprocess.run(cmd, text=True, capture_output=True)
    print(r.stdout)
    print(r.stderr)

run(["git", "log", "--oneline", "-5"])
run(["git", "status"])
run(["git", "ls-remote", "origin"])
