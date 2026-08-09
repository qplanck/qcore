from __future__ import annotations

from pathlib import Path


def test_adapter_carries_the_repository_apache_license() -> None:
    package_root = Path(__file__).parents[1]
    repository_root = package_root.parents[1]
    packaged_license = package_root / "LICENSE"
    repository_license = repository_root / "LICENSE"
    assert packaged_license.read_bytes() == repository_license.read_bytes()
