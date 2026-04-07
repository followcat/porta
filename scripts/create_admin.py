from __future__ import annotations

import argparse
import getpass

from app.db.session import get_session_factory
from app.services.auth_service import AuthService


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Porta admin user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")

    session_factory = get_session_factory()
    with session_factory() as session:
        service = AuthService(session)
        service.create_admin(args.username, password)
        session.commit()

    print(f"Created admin user: {args.username}")


if __name__ == "__main__":
    main()
