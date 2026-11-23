"""Database backup and restore (SQLite online backup API).

PostgreSQL deployments should use ``pg_dump``/``pg_restore`` (documented in
docs/OPERATIONS.md); these helpers refuse to run against non-SQLite URLs.
"""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import get_settings
from .db import init_engine

KEEP = 30


def _db_path() -> Path:
    url = get_settings().resolved_database_url
    if not url.startswith("sqlite:///"):
        raise RuntimeError("Built-in backup supports SQLite only; use pg_dump for PostgreSQL")
    return Path(url.replace("sqlite:///", "", 1))


def create_backup(label: str = "manual") -> Path:
    src = _db_path()
    d = get_settings().backup_dir
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    dest = d / f"executive_hub-{stamp}-{label}.db"
    with sqlite3.connect(src) as s, sqlite3.connect(dest) as t:
        s.backup(t)
    backups = sorted(d.glob("executive_hub-*.db"))
    for old in backups[:-KEEP]:
        old.unlink(missing_ok=True)
    return dest


def list_backups() -> list[dict]:
    d = get_settings().backup_dir
    if not d.exists():
        return []
    return [{"name": p.name, "size_bytes": p.stat().st_size,
             "created_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
            for p in sorted(d.glob("executive_hub-*.db"), reverse=True)]


def validate_backup(path: Path) -> None:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as c:
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise ValueError(f"Backup failed integrity check: {ok}")
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("alembic_version", "businesses", "opportunities", "users"):
            if t not in tables:
                raise ValueError(f"Backup is missing table '{t}'")


def restore_backup(name: str) -> Path:
    d = get_settings().backup_dir
    path = (d / name).resolve()
    if path.parent != d.resolve() or not path.exists():
        raise FileNotFoundError("Backup not found")
    validate_backup(path)
    safety = create_backup(label="pre-restore")
    target = _db_path()
    from .db import get_engine

    get_engine().dispose()
    with sqlite3.connect(path) as s, sqlite3.connect(target) as t:
        s.backup(t)
    init_engine()
    return safety
