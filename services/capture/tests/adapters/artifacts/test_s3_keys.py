from pathlib import Path

from adapters.artifacts.s3.keys import (
    archive_prefixes,
    package_key,
    staging_artifact_key,
)
from domain.capture import PageTask, TaskClaim


def test_staging_artifact_key_quotes_every_component() -> None:
    claim = TaskClaim(
        task=PageTask(
            archive_id="archive/one",
            url_key="https://example.org/a?b=1",
            url="https://example.org/a?b=1",
            depth=0,
        ),
        attempt_id="attempt/1",
        fence=1,
        lease_until=1.0,
    )

    key = staging_artifact_key(
        claim,
        "snap/1",
        Path("warcs/part one.warc.gz"),
    )

    assert key == (
        "capture-staging/archive%2Fone/"
        "https%3A%2F%2Fexample.org%2Fa%3Fb%3D1/"
        "attempt%2F1/snap%2F1/warcs/part%20one.warc.gz"
    )


def test_package_key_uses_the_package_prefix() -> None:
    assert package_key("archive/one", "manifest-digest", "package-digest") == (
        "packages/archive%2Fone/manifest-digest/package-digest.wacz"
    )


def test_archive_prefixes_cover_staging_and_packages() -> None:
    assert archive_prefixes("archive/one") == (
        "capture-staging/archive%2Fone/",
        "packages/archive%2Fone/",
    )
