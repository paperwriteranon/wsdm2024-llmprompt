import sqlite3
from sqlite3 import Error

from loguru import logger


def create_connection(db_file, auto_commit=True):
    conn = None
    try:
        conn = sqlite3.connect(db_file, autocommit=auto_commit)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        conn.commit()
        return conn
    except Error as e:
        logger.exception(e)
        raise e
