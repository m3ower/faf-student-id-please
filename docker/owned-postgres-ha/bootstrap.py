#!/opt/patroni/bin/python
"""Create only this cluster's application owner/database; never echo SQL or credentials."""
import os
import psycopg
from psycopg import sql


def bootstrap():
    with psycopg.connect(host="127.0.0.1", port=5432, user="postgres", dbname="postgres",
                         password=os.environ["HA_ADMIN_PASSWORD"], connect_timeout=3, autocommit=True) as c:
        user = os.environ["HA_APP_USER"]
        database = os.environ["HA_APP_DATABASE"]
        c.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}").format(
            sql.Identifier(user), sql.Literal(os.environ["HA_APP_PASSWORD"])))
        c.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(user)))
        c.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))


if __name__ == "__main__":
    try:
        bootstrap()
    except Exception:
        raise SystemExit("Owned database bootstrap failed") from None
