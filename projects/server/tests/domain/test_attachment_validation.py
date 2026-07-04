import pytest
from domain.attachments.validation import (
    is_allowed_content_type,
    validate_filename,
)


def test_allows_text_and_image_types():
    assert is_allowed_content_type("text/markdown") is True
    assert is_allowed_content_type("image/png") is True
    assert is_allowed_content_type("text/plain; charset=utf-8") is True


def test_rejects_disallowed_types():
    assert is_allowed_content_type("application/x-msdownload") is False


def test_validate_filename_returns_clean_leaf():
    assert validate_filename("mockup.png") == "mockup.png"


@pytest.mark.parametrize("bad", ["../escape.txt", "a/b.txt", "", "  ", "/etc/passwd", ".", ".."])
def test_validate_filename_rejects_paths_and_empty(bad):
    with pytest.raises(ValueError):
        validate_filename(bad)
