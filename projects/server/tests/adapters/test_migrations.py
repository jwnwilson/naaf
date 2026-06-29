import subprocess
from pathlib import Path


def test_alembic_upgrade_head_on_sqlite(tmp_path):
    db_file = tmp_path / "naaf.db"
    server_dir = Path(__file__).resolve().parents[2]  # projects/server
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=server_dir,
        env={"naaf_db_url": f"sqlite:///{db_file}", "PATH": __import__("os").environ["PATH"]},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    # tables exist
    import sqlite3

    con = sqlite3.connect(db_file)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"projects", "work_items", "teams", "agent_definitions"} <= tables
