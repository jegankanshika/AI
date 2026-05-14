"""CLI for the audit log.

Usage:
    DATABASE_URL=postgresql+psycopg://... python -m app.audit_cli init
    DATABASE_URL=...  python -m app.audit_cli list --application-id <id>
    DATABASE_URL=...  python -m app.audit_cli show <run_id>
"""
from __future__ import annotations

import argparse
import json
import sys

from app.audit import AuditEvent, verify_chain
from app.audit_db import (
    get_run_events, init_schema, list_runs, make_engine, make_session_factory,
)


def _engine_or_die():
    try:
        return make_engine()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)


def cmd_init(_args: argparse.Namespace) -> int:
    engine = _engine_or_die()
    init_schema(engine)
    print("audit schema initialized")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    engine = _engine_or_die()
    Session = make_session_factory(engine)
    with Session() as s:
        runs = list_runs(s, application_id=args.application_id, limit=args.limit)
    if not runs:
        print("no runs found")
        return 0
    for r in runs:
        print(f"{r['started_at']}  run={r['run_id']}  app={r['application_id'] or '-'}  "
              f"decision={r['decision'] or '?'}  events={r['n_events']}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    engine = _engine_or_die()
    Session = make_session_factory(engine)
    with Session() as s:
        rows = get_run_events(s, args.run_id)
    if not rows:
        print(f"run {args.run_id!r} not found", file=sys.stderr)
        return 1
    events = [AuditEvent(
        id=r.id, ts=r.ts,
        run_id=r.run_id, application_id=r.application_id,
        actor=r.actor, action=r.action, payload=r.payload or {},
        prev_hash=r.prev_hash, hash=r.hash,
    ) for r in rows]
    ok = verify_chain(events)
    print(f"# run {args.run_id}  chain_verified={ok}  n_events={len(events)}")
    for e in events:
        print(f"{e.ts}  {e.actor:7s}  {e.action:32s}  {json.dumps(e.payload)[:200]}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Create the audit_events table if missing.").set_defaults(fn=cmd_init)
    pl = sub.add_parser("list", help="List recent runs.")
    pl.add_argument("--application-id", default=None)
    pl.add_argument("--limit", type=int, default=20)
    pl.set_defaults(fn=cmd_list)
    ps = sub.add_parser("show", help="Show all events for a run, with chain check.")
    ps.add_argument("run_id")
    ps.set_defaults(fn=cmd_show)

    args = p.parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
