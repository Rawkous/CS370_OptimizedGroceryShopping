import os
from sshtunnel import SSHTunnelForwarder
from mysql.connector import pooling, Error

_tunnel = None
_pool = None



# SSH Tunnel helper
def _open_tunnel():
    global _tunnel

    if os.getenv("USE_SSH_TUNNEL") != "1":
        return None

    if _tunnel is None:
        print("Starting SSH tunnel to Blue")

        _tunnel = SSHTunnelForwarder(
            (os.getenv("SSH_HOST"), int(os.getenv("SSH_PORT"))),
            ssh_username=os.getenv("SSH_USER"),
            ssh_password=os.getenv("SSH_PASSWORD"),
            remote_bind_address=(
                os.getenv("REMOTE_DB_HOST"),
                int(os.getenv("REMOTE_DB_PORT"))
            ),
            local_bind_address=("127.0.0.1", 0)
        )

        _tunnel.start()
        print(f"Tunnel active on local port {tunnel_port()}")

    return _tunnel


def tunnel_port():
    return _tunnel.local_bind_port if _tunnel else None


def _db_config():
    tunnel = _open_tunnel()

    if tunnel:
        host = "127.0.0.1"
        port = tunnel.local_bind_port
    else:
        host = os.getenv("DB_HOST", "127.0.0.1")
        port = int(os.getenv("DB_PORT", "3306"))

    return {
        "host": host,
        "port": port,
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
        "autocommit": True,
        "connection_timeout": 10,
    }

def _get_pool():
    global _pool

    if _pool is None:
        cfg = _db_config()

        print("Connecting to MySQL with config:", cfg)

        try:
            _pool = pooling.MySQLConnectionPool(
                pool_name="dbpool",
                pool_size=5,
                **cfg
            )
        except Error as e:
            print("Failed to create DB pool", e)
            _pool = None

    return _pool


def query(sql: str, params=()):
    pool = _get_pool()

    if pool is None:
        raise RuntimeError(
            "Database pool is not available."
        )

    conn = pool.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()



# Simple health check
def db_smoke_ok() -> bool:
    try:
        rows = query("SELECT 1 AS ok", ())
        return rows and rows[0].get("ok") == 1
    except Exception as e:
        print("DB FAILED", e)
        return False

