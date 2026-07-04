import io


def _upload(client, wi_id, name="notes.md", data=b"# hi", ct="text/markdown", overwrite=False):
    return client.post(
        f"/work-items/{wi_id}/attachments",
        files={"file": (name, io.BytesIO(data), ct)},
        data={"overwrite": str(overwrite).lower()},
    )


def test_upload_then_list_and_download(client, seeded_work_item_id):
    up = _upload(client, seeded_work_item_id)
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["success"] is True
    att = body["data"]
    assert att["filename"] == "notes.md"
    assert att["contentType"] == "text/markdown"
    assert att["size"] == 4

    listed = client.get(f"/work-items/{seeded_work_item_id}/attachments").json()["data"]
    assert [a["filename"] for a in listed] == ["notes.md"]

    dl = client.get(f"/work-items/{seeded_work_item_id}/attachments/{att['id']}")
    assert dl.status_code == 200
    assert dl.content == b"# hi"


def test_duplicate_filename_conflicts_without_overwrite(client, seeded_work_item_id):
    _upload(client, seeded_work_item_id)
    dup = _upload(client, seeded_work_item_id)
    assert dup.status_code == 409


def test_overwrite_replaces_bytes_and_keeps_single_row(client, seeded_work_item_id):
    _upload(client, seeded_work_item_id, data=b"one")
    up2 = _upload(client, seeded_work_item_id, data=b"two-longer", overwrite=True)
    assert up2.status_code == 200
    listed = client.get(f"/work-items/{seeded_work_item_id}/attachments").json()["data"]
    assert len(listed) == 1
    assert listed[0]["size"] == len(b"two-longer")


def test_rejects_disallowed_content_type(client, seeded_work_item_id):
    r = _upload(client, seeded_work_item_id, name="a.exe", ct="application/x-msdownload")
    assert r.status_code == 415


def test_rejects_oversize_upload(client, seeded_work_item_id):
    big = b"x" * (10_485_760 + 1)
    r = _upload(client, seeded_work_item_id, name="big.txt", data=big, ct="text/plain")
    assert r.status_code == 413


def test_delete_removes_attachment(client, seeded_work_item_id):
    att = _upload(client, seeded_work_item_id).json()["data"]
    d = client.delete(f"/work-items/{seeded_work_item_id}/attachments/{att['id']}")
    assert d.status_code == 200
    listed = client.get(f"/work-items/{seeded_work_item_id}/attachments").json()["data"]
    assert listed == []


def test_upload_to_other_owners_item_is_404(client_other_owner, seeded_work_item_id):
    r = _upload(client_other_owner, seeded_work_item_id)
    assert r.status_code == 404


def test_cannot_access_attachment_via_wrong_work_item(
    client, seeded_work_item_id, second_work_item_id
):
    # Upload to work item A (seeded_work_item_id); both items share one owner.
    att = _upload(client, seeded_work_item_id).json()["data"]

    # DELETE via work item B's URL must 404 and NOT touch A's row.
    d = client.delete(f"/work-items/{second_work_item_id}/attachments/{att['id']}")
    assert d.status_code == 404
    still = client.get(f"/work-items/{seeded_work_item_id}/attachments").json()["data"]
    assert [a["id"] for a in still] == [att["id"]]

    # GET download via work item B's URL must 404 too.
    dl = client.get(f"/work-items/{second_work_item_id}/attachments/{att['id']}")
    assert dl.status_code == 404


def test_download_forces_attachment_disposition(client, seeded_work_item_id):
    """Download response must use 'attachment' disposition, never 'inline'.

    Serving SVG inline at the app origin allows stored-XSS via embedded <script>.
    """
    att = _upload(client, seeded_work_item_id).json()["data"]
    dl = client.get(f"/work-items/{seeded_work_item_id}/attachments/{att['id']}")
    assert dl.status_code == 200
    assert dl.headers["content-disposition"].startswith("attachment")


def test_download_encodes_special_chars_in_filename(client, seeded_work_item_id):
    """Filename with spaces/quotes must be percent-encoded (RFC 6266 filename*=UTF-8'')."""
    att = _upload(
        client, seeded_work_item_id, name='my notes "v2".md', data=b"x", ct="text/markdown"
    ).json()["data"]
    dl = client.get(f"/work-items/{seeded_work_item_id}/attachments/{att['id']}")
    assert dl.status_code == 200
    cd = dl.headers["content-disposition"]
    # Must not contain a raw double-quote (would break the header)
    assert '"' not in cd
    assert "attachment" in cd
