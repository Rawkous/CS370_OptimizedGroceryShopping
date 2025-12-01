import pytest
from python.app import db


def test_db_module_loads():
    assert db is not None


def test_db_config_basic(monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_USER", "testuser")
    monkeypatch.setenv("DB_PASSWORD", "pw")
    monkeypatch.setenv("DB_NAME", "dbname")
    monkeypatch.setenv("USE_SSH_TUNNEL", "0")

    cfg = db._db_config()
    assert cfg["host"] == "localhost"
    assert cfg["port"] == 3306
    assert cfg["user"] == "testuser"
    assert cfg["password"] == "pw"
    assert cfg["database"] == "dbname"


def test_query_raises_when_pool_missing(monkeypatch):
    def fake_pool():
        return None

    monkeypatch.setattr(db, "_get_pool", fake_pool)

    with pytest.raises(RuntimeError):
        db.query("SELECT 1")

