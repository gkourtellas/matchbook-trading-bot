import subprocess

print("Cleaning up old Docker images/containers/cache...")
subprocess.run(["docker", "system", "prune", "-a", "-f"])

print("\nDisk usage now:")
subprocess.run(["df", "-h"])
