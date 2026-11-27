from pathlib import Path
from zipfile import ZipFile

import pytest
from support.wacz import warc_bytes

from crawler.wacz import create_wacz, validate_wacz


def test_create_and_validate_wacz(tmp_path: Path) -> None:
    warc = tmp_path / "capture.warc.gz"
    warc.write_bytes(warc_bytes())

    package = tmp_path / "package.wacz"

    create_wacz([warc], package)

    with ZipFile(package) as archive:
        assert "archive/capture.warc.gz" in archive.namelist()
        assert "indexes/index.cdx.gz" in archive.namelist()

    validate_wacz(package, ["capture.warc.gz"])


def test_validate_wacz_rejects_missing_archive_entry(tmp_path: Path) -> None:
    warc = tmp_path / "capture.warc.gz"
    warc.write_bytes(warc_bytes())

    package = tmp_path / "package.wacz"

    create_wacz([warc], package)

    with pytest.raises(RuntimeError, match="archive entries do not match"):
        validate_wacz(package, ["other.warc.gz"])
