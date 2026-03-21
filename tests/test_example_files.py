"""Test that every .rgl file in docs/examples/ runs without error.

If a matching .expected file exists, stdout is checked against it.
This ensures README/tutorial examples stay valid as the language evolves.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "docs" / "examples"


def _example_cases() -> list[pytest.param]:
    cases = []
    for rgl in sorted(EXAMPLES_DIR.glob("*.rgl")):
        expected_file = rgl.with_suffix(".expected")
        expected = expected_file.read_text() if expected_file.exists() else None
        cases.append(pytest.param(rgl, expected, id=rgl.stem))
    return cases


@pytest.mark.parametrize("rgl_file,expected_output", _example_cases())
def test_example(rgl_file: Path, expected_output: str | None):
    result = subprocess.run(
        [sys.executable, "-m", "rigel.driver", "run", str(rgl_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Example {rgl_file.name} failed:\n{result.stderr}"
    )
    if expected_output is not None:
        assert result.stdout == expected_output, (
            f"Example {rgl_file.name} output mismatch:\n"
            f"  expected: {expected_output!r}\n"
            f"  got:      {result.stdout!r}"
        )
