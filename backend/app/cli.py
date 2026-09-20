"""管理脚本。用法：cd backend && python -m app.cli <子命令> --help"""
from __future__ import annotations

import argparse
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import InviteCode, StylePreset, User
from app.services.palettes import seed_palettes


def _user_or_die(db: Session, username: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        print(f"没有这个用户：{username}", file=sys.stderr)
        raise SystemExit(2)
    return user


def cmd_invite(db: Session, count: int, uses: int) -> int:
    for _ in range(count):
        code = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")[:12].upper()
        db.add(InviteCode(code=code, max_uses=uses))
        print(code)
    db.flush()
    return count


def cmd_quota(db: Session, username: str, add: int) -> int:
    user = _user_or_die(db, username)
    user.ai_quota += add
    db.flush()
    left = user.ai_quota - user.ai_used
    print(f"{username}: 总额度 {user.ai_quota}，已用 {user.ai_used}，剩余 {left}")
    return left


def cmd_seed_palettes(db: Session) -> int:
    n = seed_palettes(db)
    print(f"写入 {n} 个色号")
    return n


def cmd_preset(db: Session, name: str, prompt: str) -> StylePreset:
    sp = StylePreset(name=name, prompt=prompt, params={})
    db.add(sp)
    db.flush()
    print(f"已创建风格预设 {sp.id} · {name}")
    return sp


def cmd_admin(db: Session, username: str) -> None:
    user = _user_or_die(db, username)
    user.is_admin = True
    db.flush()
    print(f"{username} 已设为管理员")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("invite", help="生成邀请码")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--uses", type=int, default=1)

    p = sub.add_parser("quota", help="增加 AI 额度")
    p.add_argument("--user", required=True)
    p.add_argument("--add", type=int, required=True)

    sub.add_parser("seed-palettes", help="把色卡灌进数据库")

    p = sub.add_parser("preset", help="创建风格预设")
    p.add_argument("--name", required=True)
    p.add_argument("--prompt", required=True)

    p = sub.add_parser("admin", help="把用户设为管理员")
    p.add_argument("--user", required=True)

    args = ap.parse_args(argv)
    db = SessionLocal()
    try:
        if args.cmd == "invite":
            cmd_invite(db, args.count, args.uses)
        elif args.cmd == "quota":
            cmd_quota(db, args.user, args.add)
        elif args.cmd == "seed-palettes":
            cmd_seed_palettes(db)
        elif args.cmd == "preset":
            cmd_preset(db, args.name, args.prompt)
        elif args.cmd == "admin":
            cmd_admin(db, args.user)
        db.commit()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
