def is_html_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return True

    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()

    return media_type in {"text/html", "application/xhtml+xml"}


def is_pdf_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False

    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()

    return media_type == "application/pdf"
