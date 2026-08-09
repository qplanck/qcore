from __future__ import annotations

import pytest

from tools.check_python_runtime import _validate_license, runtime_closure


def test_runtime_dependency_closure_has_allowed_licenses() -> None:
    names = {distribution.metadata["Name"].lower() for distribution in runtime_closure()}

    assert names == {"numpy", "qplanck"}


def test_license_policy_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="unsupported tokens"):
        _validate_license("unsafe", "GPL-3.0-only")
