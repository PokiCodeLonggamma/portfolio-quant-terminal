"""Generate a bcrypt hash for a password — used to populate QT_ADMIN_PASSWORD_HASH.

Usage::

    python scripts/hash_password.py
    Password: ***************
    bcrypt: $2b$12$abc...

Then paste the hash into your .env::

    QT_ADMIN_PASSWORD_HASH=$2b$12$abc...

(passlib + python-jose come with the [api] extras.)
"""
import getpass
import sys

import bcrypt


def main() -> int:
    if not sys.stdin.isatty():
        print("Run interactively, not in a pipe.", file=sys.stderr)
        return 1
    pwd = getpass.getpass("Password: ")
    if not pwd:
        print("Empty password — aborting.", file=sys.stderr)
        return 1
    confirm = getpass.getpass("Confirm:  ")
    if confirm != pwd:
        print("Mismatch — aborting.", file=sys.stderr)
        return 1
    hashed = bcrypt.hashpw(pwd.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode("utf-8")
    print("\nbcrypt hash (paste into .env as QT_ADMIN_PASSWORD_HASH):")
    print(hashed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
