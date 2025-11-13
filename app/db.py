# app/db.py
import os
from mysql.connector import pooling, Error  # type: ignore

_pool = None

def _db_config():
    cfg = {
        "host": os.getenv("DB_HOST", "blue.cs.sonoma.edu"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
        "autocommit": True,
        "connection_timeout": 10,
    }
    missing = [
        k
        for k, v in (
            ("DB_USER", cfg["user"]),
            ("DB_PASSWORD", cfg["password"]),
            ("DB_NAME", cfg["database"]),
        )
        if not v
    ]
    if missing:
        print(f"❌ Missing required DB env vars: {', '.join(missing)}")
        print("   Make sure your .env has DB_USER, DB_PASSWORD, DB_NAME.")
    return cfg

def _get_pool():
    global _pool
    if _pool is None:
        cfg = _db_config()
        try:
            _pool = pooling.MySQLConnectionPool(pool_name="dbpool", pool_size=5, **cfg)
        except Error as e:
            print("❌ Failed to create DB pool:", e)
            _pool = None
    return _pool

def query(sql: str, params=()):
    pool = _get_pool()
    if pool is None:
        raise RuntimeError("Database pool is not available. Check DB env vars / tunnel / connectivity.")
    conn = pool.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        try:
            cur.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass

def db_smoke_ok() -> bool:
    try:
        rows = query("SELECT 1 AS ok", ())
        return bool(rows and rows[0].get("ok") == 1)
    except Exception as e:
        print("❌ DB FAILED:", e)
        return False
