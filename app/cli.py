# CLI: Haushalte + Nutzer anlegen (Passwort-Hash mit PBKDF2, kein Klartext).
# Aufruf: python -m app.cli add-user <household> <username>

from __future__ import annotations

import sys

from sqlalchemy import select

from .main import hash_password, SessionLocal  # noqa: E402
from .models import Household, User


def add_user(household_name: str, username: str, password: str) -> None:
    db = SessionLocal()
    hh = db.execute(select(Household).where(
        Household.name == household_name)).scalar_one_or_none()
    if hh is None:
        hh = Household(name=household_name)
        db.add(hh)
        db.flush()
    exists = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if exists:
        print(f"User {username!r} existiert bereits.")
        return
    db.add(User(username=username, password_hash=hash_password(password),
                household_id=hh.id))
    db.commit()
    print(f"User {username!r} im Haushalt {household_name!r} angelegt.")


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "add-user" and len(argv) >= 4:
        import getpass
        household, username = argv[2], argv[3]
        password = getpass.getpass("Passwort: ")
        add_user(household, username, password)
        return 0
    print("Usage: python -m app.cli add-user <household> <username>")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
