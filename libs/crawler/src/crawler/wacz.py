import io
from collections.abc import Callable, Sequence
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import cast
from zipfile import ZipFile

from wacz.main import main  # pyright: ignore[reportMissingTypeStubs, reportUnknownVariableType]

_run_wacz = cast(Callable[[list[str]], int], main)


def create_wacz(war_files: Sequence[Path], output: Path) -> None:
    """Create a validated-layout WACZ from previously verified WARC files."""

    if not war_files:
        raise ValueError("a WACZ requires at least one WARC file")

    status = run(
        [
            "create",
            "--output",
            str(output),
            "--detect-pages",
            *(str(path) for path in war_files),
        ]
    )

    if status != 0 or not output.is_file():
        raise RuntimeError("WACZ creation failed")


def validate_wacz(path: Path, expected_archives: Sequence[str]) -> None:
    """Validate WACZ structure and confirm it contains exactly the selected WARCs."""

    if run(["validate", "--file", str(path)]) != 0:
        raise RuntimeError("WACZ validation failed")

    expected = {f"archive/{name}" for name in expected_archives}

    with ZipFile(path) as archive:
        names = set(archive.namelist())

    if not {"datapackage.json", "indexes/index.cdx.gz", "indexes/index.idx"} <= names:
        raise RuntimeError("WACZ is missing required package entries")

    actual = {name for name in names if name.startswith("archive/")}

    if actual != expected:
        raise RuntimeError("WACZ archive entries do not match the committed manifest")


def run(arguments: Sequence[str]) -> int:
    output = io.StringIO()

    with redirect_stdout(output), redirect_stderr(output):
        status = _run_wacz(list(arguments))

    return int(status)


__all__ = [
    "create_wacz",
    "validate_wacz",
]
