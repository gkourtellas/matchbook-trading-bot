import subprocess

commands = [
    ["docker", "system", "prune", "-a", "-f", "--volumes"],
    ["docker", "builder", "prune", "-a", "-f"],
]

for cmd in commands:
    subprocess.run(cmd, check=True)