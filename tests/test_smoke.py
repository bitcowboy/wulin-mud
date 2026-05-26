"""Smoke test: verifies the package is importable and version is sane.

This is the only test required to pass on Day 0. Real tests come with
real code under v0.1 milestones (see docs/roadmap.md).
"""

import wulin_mud


def test_package_imports() -> None:
    assert wulin_mud.__version__ == "0.1.0a0"
