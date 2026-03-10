"""Detect changed files via git diff."""
import subprocess
from pathlib import Path


def get_changed_files(since: str = "HEAD") -> list[str]:
    """Return files changed since given ref. Defaults to uncommitted changes."""
    cmds = [
        ["git", "diff", "--name-only", since],
        ["git", "diff", "--cached", "--name-only"],   # staged
        ["git", "diff", "--name-only"],                # unstaged
    ]
    if since != "HEAD":
        cmds = [["git", "diff", "--name-only", since]]

    seen = set()
    files = []
    for cmd in cmds:
        out = subprocess.run(cmd, capture_output=True, text=True)
        for f in out.stdout.strip().splitlines():
            f = f.strip()
            if f and f not in seen and Path(f).suffix in (".py", ".ts", ".tsx", ".js", ".jsx"):
                seen.add(f)
                files.append(f)
    return files


def get_changed_py(since: str = "HEAD") -> list[str]:
    return [f for f in get_changed_files(since) if f.endswith(".py")]


def get_changed_frontend(since: str = "HEAD") -> list[str]:
    return [f for f in get_changed_files(since) if f.endswith((".ts", ".tsx", ".js", ".jsx"))]
