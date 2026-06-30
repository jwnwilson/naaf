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


def test_migration_remaps_legacy_status(tmp_path):
    import os
    import sqlite3
    import subprocess
    from pathlib import Path

    db = tmp_path / "naaf.db"
    server = Path(__file__).resolve().parents[2]
    env = {"naaf_db_url": f"sqlite:///{db}", "PATH": os.environ["PATH"]}
    # migrate to the FIRST revision only, insert a legacy row, then upgrade head
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "0001_initial"],
        cwd=server,
        env=env,
        check=True,
    )
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO work_items (id, owner_id, project_id, kind, title, body, "
        "acceptance_criteria, status, created_at, updated_at) VALUES "
        "('w1','u1','p1','task','x','','[]','to_do','2026-01-01','2026-01-01')"
    )
    con.commit()
    con.close()
    r = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=server,
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db)
    status = con.execute("SELECT status FROM work_items WHERE id='w1'").fetchone()[0]
    cols = {r[1] for r in con.execute("PRAGMA table_info(work_items)")}
    assert status == "todo"
    assert "priority" in cols


def test_migration_creates_run_tables(tmp_path):
    import os
    import sqlite3
    import subprocess
    from pathlib import Path

    db = tmp_path / "naaf.db"
    server = Path(__file__).resolve().parents[2]
    env = {"naaf_db_url": f"sqlite:///{db}", "PATH": os.environ["PATH"]}
    r = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=server,
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db)
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "run_events", "bus_messages"} <= tables
