# app/tunnel.py
import os
import atexit

_TUNNEL = None

try:
    import sshtunnel as _sshn  # type: ignore
    from sshtunnel import SSHTunnelForwarder  # type: ignore
except Exception:
    SSHTunnelForwarder = None
    _sshn = None

def maybe_start_tunnel():
    """
    Start an SSH tunnel to the remote MySQL host and rewrite DB_HOST/DB_PORT to the
    local forward so the DB pool can connect. Safe to call multiple times.
    """
    if os.getenv("USE_SSH_TUNNEL", "1") != "1":
        return

    if SSHTunnelForwarder is None:
        print("⚠️  sshtunnel not installed; set USE_SSH_TUNNEL=0 or `pip install sshtunnel`.")
        return

    if _sshn:
        _sshn.SSH_TIMEOUT = float(os.getenv("SSH_TIMEOUT", "5.0"))
        _sshn.TUNNEL_TIMEOUT = float(os.getenv("TUNNEL_TIMEOUT", "15.0"))

    global _TUNNEL
    if _TUNNEL:
        return

    ssh_host     = os.getenv("SSH_HOST", "blue.cs.sonoma.edu")
    ssh_port     = int(os.getenv("SSH_PORT", "22"))
    ssh_user     = os.getenv("SSH_USER")
    ssh_password = os.getenv("SSH_PASSWORD")
    ssh_pkey     = os.getenv("SSH_PKEY")

    remote_host  = os.getenv("REMOTE_DB_HOST", "127.0.0.1")
    remote_port  = int(os.getenv("REMOTE_DB_PORT", "3306"))
    local_port   = int(os.getenv("LOCAL_TUNNEL_PORT", "3307"))

    if not ssh_user or (not ssh_password and not ssh_pkey):
        print("❌ USE_SSH_TUNNEL=1 but SSH_USER and SSH_PASSWORD/SSH_PKEY not set; skipping tunnel.")
        return

    try:
        _TUNNEL = SSHTunnelForwarder(
            (ssh_host, ssh_port),
            ssh_username=ssh_user,
            ssh_password=ssh_password or None,
            ssh_pkey=ssh_pkey or None,
            remote_bind_address=(remote_host, remote_port),
            local_bind_address=("127.0.0.1", local_port),
        )
        _TUNNEL.start()
    except Exception as e:
        _TUNNEL = None
        print(f"❌ Failed to start SSH tunnel: {e}")
        return

    os.environ["DB_HOST"] = "127.0.0.1"
    os.environ["DB_PORT"] = str(_TUNNEL.local_bind_port)
    print(f"🔗 SSH tunnel started → 127.0.0.1:{_TUNNEL.local_bind_port}")

@atexit.register
def _close_tunnel():
    global _TUNNEL
    if _TUNNEL:
        try:
            _TUNNEL.stop()
            print("🔚 SSH tunnel stopped")
        except Exception:
            pass
        finally:
            _TUNNEL = None
