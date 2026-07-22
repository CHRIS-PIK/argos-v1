from __future__ import annotations
from contextlib import contextmanager
import mysql.connector
from app.config import settings

@contextmanager
def connection():
    cnx = mysql.connector.connect(
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        autocommit=False,
    )
    try:
        yield cnx
        cnx.commit()
    except Exception:
        cnx.rollback()
        raise
    finally:
        cnx.close()
