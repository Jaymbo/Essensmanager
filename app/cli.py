# CLI: Haushalte + Nutzer verwalten (Passwort-Hashes mit PBKDF2, kein Klartext).
# Aufruf: python -m app.cli add-user <household> <username>
#         python -m app.cli set-password <username>

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


def set_password(username: str, password: str) -> None:
    """Setzt/überschreibt das Passwort eines bestehenden Users."""
    db = SessionLocal()
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        print(f"User {username!r} existiert nicht. "
              f"Anlegen mit: python -m app.cli add-user <haushalt> {username}")
        return
    user.password_hash = hash_password(password)
    db.commit()
    print(f"Passwort für {username!r} gesetzt.")


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "add-user" and len(argv) >= 4:
        import getpass
        household, username = argv[2], argv[3]
        password = getpass.getpass("Passwort: ")
        add_user(household, username, password)
        return 0
    if len(argv) >= 2 and argv[1] == "set-password" and len(argv) >= 3:
        import getpass
        username = argv[2]
        password = getpass.getpass("Neues Passwort: ")
        confirm = getpass.getpass("Wiederholen: ")
        if password != confirm:
            print("Passwörter stimmen nicht überein – abgebrochen.")
            return 1
        set_password(username, password)
        return 0
    print("Usage: python -m app.cli add-user <household> <username>\n"
          "       python -m app.cli set-password <username>")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
