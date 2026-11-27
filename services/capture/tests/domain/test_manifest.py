from domain.capture import manifest_key


def test_manifest_key_uses_the_digest() -> None:
    digest = "0" * 64

    assert manifest_key("archive-1", digest) == f"manifests/archive-1/{digest}.json"


def test_manifest_key_quotes_the_archive_id() -> None:
    digest = "0" * 64

    assert manifest_key("archive/1", digest) == f"manifests/archive%2F1/{digest}.json"
