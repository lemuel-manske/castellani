from utils.web import is_html_content_type, is_pdf_content_type


def test_html_content_type_accepts_html_media_types() -> None:
    assert is_html_content_type("text/html; charset=utf-8")
    assert is_html_content_type("application/xhtml+xml")


def test_html_content_type_rejects_binary_media_types() -> None:
    assert not is_html_content_type("application/pdf")
    assert not is_html_content_type("application/octet-stream")


def test_html_content_type_defaults_to_html_when_missing() -> None:
    assert is_html_content_type(None)


def test_pdf_content_type_accepts_pdf_media_type() -> None:
    assert is_pdf_content_type("application/pdf; charset=binary")
    assert not is_pdf_content_type("application/octet-stream")
