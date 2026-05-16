from __future__ import annotations

import argparse
import sys

from .gate import ProGate
from .team_vault import TeamVault

_INFO_TEXT = """\
CTX Pro -- Pricing

Free (local, MIT)
  - vault.db grows locally per-user
  - BM25 + semantic search
  - No data leaves machine

Pro ($15-20/mo) -- key prefix: CTX-PRO-
  - Cloud vault sync
  - Team shared memory
  - Better retrieval model

Team ($49-99/mo) -- key prefix: CTX-TEAM-
  - Private team vault (org isolation)
  - Admin panel + audit trail
  - Custom retrieval tuning

Get a key: https://ctx-retriever.dev/pro  (coming soon)
"""


def cmd_info(args: argparse.Namespace) -> int:
    print(_INFO_TEXT, end="")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    gate = ProGate()
    if gate.is_active():
        info = gate.info()
        email = info.get("email") or "(no email)"
        tier = info.get("tier", "pro")
        activated_at = info.get("activated_at", "")
        print(f"Pro: active (tier={tier}, email={email})")
        if activated_at:
            print(f"  Activated: {activated_at}")
    else:
        print("Pro: free  (no license -- run `ctx-pro info` to learn about Pro features)")
    return 0


def cmd_activate(args: argparse.Namespace) -> int:
    key = args.key
    email = args.email or ""
    if not (key.startswith("CTX-PRO-") or key.startswith("CTX-TEAM-")):
        print(f"Error: invalid key format. Expected CTX-PRO-... or CTX-TEAM-...", file=sys.stderr)
        return 1
    gate = ProGate()
    gate.activate(key, email)
    tier = gate.tier()
    print(f"Activated {tier} license.")
    if email:
        print(f"  Email: {email}")
    return 0


def cmd_deactivate(args: argparse.Namespace) -> int:
    gate = ProGate()
    if not gate.is_active():
        print("No active license to deactivate.")
        return 0
    gate.deactivate()
    print("License deactivated.")
    return 0


def cmd_team_vault_init(args: argparse.Namespace) -> int:
    gate = ProGate()
    if not gate.is_active():
        print("Error: Pro license required. Run `ctx-pro activate <key>`.", file=sys.stderr)
        return 1
    gate.set_team_vault(args.url, args.token)
    tv = TeamVault(gate)
    print(f"Team vault configured: {args.url}")
    print(f"Status: {tv.status()}")
    return 0


def cmd_team_vault_push(args: argparse.Namespace) -> int:
    gate = ProGate()
    if not gate.is_active():
        print("Error: Pro license required.", file=sys.stderr)
        return 1
    tv = TeamVault(gate)
    try:
        result = tv.push(limit=getattr(args, "limit", 200))
        pushed = result.get("pushed", 0)
        total = result.get("total", 0)
        print(f"Pushed {pushed}/{total} messages to team vault.")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_team_vault_pull(args: argparse.Namespace) -> int:
    gate = ProGate()
    if not gate.is_active():
        print("Error: Pro license required.", file=sys.stderr)
        return 1
    tv = TeamVault(gate)
    try:
        result = tv.pull(limit=getattr(args, "limit", 500))
        pulled = result.get("pulled", 0)
        total = result.get("total", 0)
        print(f"Pulled {pulled}/{total} messages into local vault.")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_team_vault_status(args: argparse.Namespace) -> int:
    gate = ProGate()
    tv = TeamVault(gate)
    print(f"Team vault: {tv.status()}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="ctx-pro",
        description="CTX Pro license management.",
    )
    sub = p.add_subparsers(dest="command")

    sub.add_parser("info", help="Show pricing tiers and feature comparison.")
    sub.add_parser("status", help="Show current activation status.")

    act = sub.add_parser("activate", help="Activate a license key.")
    act.add_argument("key", help="License key (CTX-PRO-... or CTX-TEAM-...)")
    act.add_argument("--email", default="", help="Email associated with the license.")

    sub.add_parser("deactivate", help="Remove the current license.")

    # team-vault subcommand group
    tv_p = sub.add_parser("team-vault", help="Team shared vault management.")
    tv_sub = tv_p.add_subparsers(dest="tv_command")

    tv_init = tv_sub.add_parser("init", help="Configure team vault Turso endpoint.")
    tv_init.add_argument("--url", required=True, help="Turso DB URL (https://...turso.io)")
    tv_init.add_argument("--token", required=True, help="Turso write token.")

    tv_push = tv_sub.add_parser("push", help="Push local vault messages to team vault.")
    tv_push.add_argument("--limit", type=int, default=200, help="Max messages to push (default: 200).")

    tv_pull = tv_sub.add_parser("pull", help="Pull team vault messages into local vault.")
    tv_pull.add_argument("--limit", type=int, default=500, help="Max messages to pull (default: 500).")

    tv_sub.add_parser("status", help="Show team vault configuration status.")

    args = p.parse_args()

    if args.command == "info":
        return cmd_info(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "activate":
        return cmd_activate(args)
    if args.command == "deactivate":
        return cmd_deactivate(args)
    if args.command == "team-vault":
        tv_cmd = getattr(args, "tv_command", None)
        if tv_cmd == "init":
            return cmd_team_vault_init(args)
        if tv_cmd == "push":
            return cmd_team_vault_push(args)
        if tv_cmd == "pull":
            return cmd_team_vault_pull(args)
        if tv_cmd == "status":
            return cmd_team_vault_status(args)
        tv_p.print_help()
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
