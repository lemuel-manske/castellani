from domain.capture import (
    capture_page_message_id,
    page_captured_message_id,
    release_page_message_id,
)


def test_capture_page_message_id_is_byte_stable() -> None:
    assert capture_page_message_id("archive-1", "url-1") == ("189af2d5-3300-50f2-a463-c5a34161713f")


def test_page_captured_message_id_is_byte_stable() -> None:
    assert page_captured_message_id("archive-1", "snapshot-1") == (
        "95ac28ec-7ae2-5154-92bb-f000a6dc513c"
    )


def test_release_page_message_id_is_byte_stable() -> None:
    assert release_page_message_id("archive-1", "url-1", "attempt-1", 2) == (
        "b914e443-bc1d-5419-b732-79f6f637148b"
    )
