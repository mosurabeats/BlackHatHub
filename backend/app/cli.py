"""Owner/maintenance command line: python -m app.cli <command>

Commands:
  init                 create/upgrade database and seed reference data
  reset-password USER  set a new password for USER (prompts)
  reset-pin            reset the private vault PIN (prompts; requires host access)
  backup               create a database backup
  restore NAME         restore a named backup (a safety backup is taken first)
  list-backups
  run-cycle            run one full research cycle synchronously (no web server)
  run-source KEY       run one research source synchronously
  status               print system status
"""
from __future__ import annotations

import getpass
import json
import sys

from sqlalchemy import select


def _init():
    from .main import bootstrap

    bootstrap()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    cmd, args = argv[0], argv[1:]
    _init()
    from .db import session_scope
    from .models import AuthSession, Source, User, VaultConfig
    from .security import hash_secret, password_problems, pin_problems

    if cmd == "init":
        print("Database ready.")
    elif cmd == "reset-password":
        with session_scope() as db:
            u = db.execute(select(User).where(User.username == args[0])).scalars().first()
            if not u:
                print("No such user")
                return 1
            pw = getpass.getpass("New password: ")
            if p := password_problems(pw, u.username):
                print(" ".join(p))
                return 1
            u.password_hash = hash_secret(pw)
            u.failed_logins, u.locked_until = 0, None
            for s in db.execute(select(AuthSession).where(AuthSession.user_id == u.id)).scalars():
                s.revoked = True
        print("Password updated; all sessions signed out.")
    elif cmd == "reset-pin":
        pin = getpass.getpass("New vault PIN (4-8 digits): ")
        if p := pin_problems(pin):
            print(" ".join(p))
            return 1
        with session_scope() as db:
            v = db.get(VaultConfig, 1)
            v.pin_hash, v.failed_attempts, v.locked_until, v.is_initial_pin = hash_secret(pin), 0, None, False
        print("Vault PIN reset.")
    elif cmd == "backup":
        from .backup import create_backup

        print(create_backup("cli"))
    elif cmd == "list-backups":
        from .backup import list_backups

        print(json.dumps(list_backups(), indent=2))
    elif cmd == "restore":
        from .backup import restore_backup

        print("Safety backup:", restore_backup(args[0]))
    elif cmd in ("run-cycle", "run-source"):
        from .jobs import handlers  # noqa: F401
        from .jobs.scheduler import Scheduler, enqueue

        with session_scope() as db:
            if cmd == "run-cycle":
                enqueue(db, "research_cycle", triggered_by="cli")
            else:
                src = db.execute(select(Source).where(Source.key == args[0])).scalars().first()
                if not src:
                    print("Unknown source key")
                    return 1
                enqueue(db, "research_source", business_id=src.business_id, source_id=src.id, triggered_by="cli")
        sch = Scheduler(worker_threads=1)
        for _ in range(200):
            res = sch.tick(run_inline=True, schedules=False)
            if not res:
                from datetime import datetime, timezone

                from .models import Job

                with session_scope() as db:  # release deferred jobs immediately in CLI mode
                    deferred = db.execute(select(Job).where(Job.status == "queued")).scalars().all()
                    if not deferred:
                        break
                    for j in deferred:
                        j.next_attempt_at = datetime.now(timezone.utc)
            print("jobs:", res)
    elif cmd == "status":
        from .models import Job, Opportunity

        with session_scope() as db:
            print("opportunities:", db.query(Opportunity).count(), "jobs:", db.query(Job).count())
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
