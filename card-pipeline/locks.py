"""
locks.py — one writer per slug (EDITORIALIZE_2 items 90 and 91). Pure stdlib.

    import locks
    with locks.acquire(slug):                 # raises locks.LockHeld when another live agent holds the slug
        ... write runs/<slug>/ ...

    lk = locks.acquire(slug, stale_after=1800)   # also usable without `with`
    lk.release()                                 # or locks.release(slug) / locks.release(lk)

A lock is a file `runs/.locks/<slug>.lock` created with O_CREAT|O_EXCL (atomic), holding
{slug, owner, pid, host, ts}. It is taken over, never waited on, when it is stale: older than `stale_after` seconds,
or written by a process on this host that no longer exists. Releasing only removes a lock this holder wrote.

    locks.scratch(agent)                      # item 91: runs/.scratch/<agent>/ — a directory per agent, never shared
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import socket
import time
import uuid
from typing import Optional

V2 = pathlib.Path(__file__).resolve().parent
LOCK_DIR = V2 / "runs" / ".locks"
SCRATCH_DIR = V2 / "runs" / ".scratch"
STALE_AFTER = 1800.0                 # seconds; a card build is minutes, so half an hour of silence is a dead agent
_SAFE = re.compile(r"[^A-Za-z0-9._#-]+")


class LockHeld(RuntimeError):
    def __init__(self, slug: str, holder: dict):
        self.slug, self.holder = slug, holder
        super().__init__(f"slug {slug!r} is locked by {holder.get('owner')!r} (pid {holder.get('pid')}, "
                         f"{holder.get('age', 0):.0f}s old)")


def safe(name: str) -> str:
    """A slug or agent name as one path component: no separators, no leading dot, never empty."""
    s = _SAFE.sub("_", str(name)).lstrip(".")
    if not s:
        raise ValueError(f"empty name {name!r}")
    return s


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read(path: pathlib.Path) -> Optional[dict]:
    try:
        d = json.loads(path.read_text())
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def is_stale(info: Optional[dict], now: float, stale_after: float = STALE_AFTER) -> bool:
    if not info or not isinstance(info.get("ts"), (int, float)):
        return True                                           # unreadable or half-written: nobody owns it
    if now - info["ts"] > stale_after:
        return True
    if info.get("host") == socket.gethostname() and isinstance(info.get("pid"), int) and not _pid_alive(info["pid"]):
        return True
    return False


class Lock:
    def __init__(self, slug: str, path: pathlib.Path, token: str):
        self.slug, self.path, self.token, self.released = slug, path, token, False

    def release(self) -> bool:
        """Remove the lock if it is still ours. Returns whether a file was removed."""
        if self.released:
            return False
        self.released = True
        info = _read(self.path)
        if info and info.get("token") == self.token:
            try:
                self.path.unlink()
                return True
            except FileNotFoundError:
                return False
        return False

    def __enter__(self) -> "Lock":
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def acquire(slug: str, owner: Optional[str] = None, lock_dir: Optional[pathlib.Path] = None,
            stale_after: float = STALE_AFTER, now: Optional[float] = None) -> Lock:
    """Take the lock for `slug` or raise LockHeld. A stale lock is replaced."""
    d = pathlib.Path(lock_dir or LOCK_DIR)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{safe(slug)}.lock"
    t = time.time() if now is None else now
    token = uuid.uuid4().hex
    info = {"slug": slug, "owner": owner or os.environ.get("CLAUDE_AGENT_ID") or f"pid{os.getpid()}", "pid": os.getpid(),
            "host": socket.gethostname(), "ts": t, "token": token}
    for _ in range(3):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            held = _read(path)
            if not is_stale(held, t, stale_after):
                raise LockHeld(slug, {**(held or {}), "age": t - (held or {}).get("ts", t)})
            # take over: remove the stale file, then race for the O_EXCL create again
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
            continue
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(info))
        return Lock(slug, path, token)
    raise LockHeld(slug, {"owner": "another agent taking over a stale lock", "age": 0})


def release(lock_or_slug, lock_dir: Optional[pathlib.Path] = None) -> bool:
    """release(lock) or release(slug). By slug it removes the file whatever its token (an operator clearing a lock)."""
    if isinstance(lock_or_slug, Lock):
        return lock_or_slug.release()
    path = pathlib.Path(lock_dir or LOCK_DIR) / f"{safe(lock_or_slug)}.lock"
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def held(slug: str, lock_dir: Optional[pathlib.Path] = None, stale_after: float = STALE_AFTER,
         now: Optional[float] = None) -> Optional[dict]:
    """The live holder of `slug`, or None."""
    path = pathlib.Path(lock_dir or LOCK_DIR) / f"{safe(slug)}.lock"
    info = _read(path)
    t = time.time() if now is None else now
    return None if (not path.exists() or is_stale(info, t, stale_after)) else info


def scratch(agent: str, root: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Item 91: the agent's own scratch directory. Each agent name maps to one directory and nothing else writes there;
    a name that would escape the root, or the shared names, is refused."""
    if str(agent).strip().lower() in {"", "shared", "tmp", "scratch", "common", "all"}:
        raise ValueError(f"{agent!r} is a shared name; scratch directories are per agent")
    p = pathlib.Path(root or SCRATCH_DIR) / safe(agent)
    p.mkdir(parents=True, exist_ok=True)
    return p
