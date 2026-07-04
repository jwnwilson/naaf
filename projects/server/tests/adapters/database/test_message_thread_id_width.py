from adapters.database.orm import MessageRow


def test_message_thread_id_fits_project_thread_ids():
    # Work-item thread ids are 32-char hex, but project threads are
    # "project:<32-hex>" = 40 chars. The column must hold them — Postgres enforces
    # varchar length (SQLite does not), so a 32-wide column truncates in prod.
    assert MessageRow.__table__.c.thread_id.type.length >= 40
