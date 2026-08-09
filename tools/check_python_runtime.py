"""Verify installed core runtime dependencies and their SPDX license policy."""

from __future__ import annotations

import re
from importlib import metadata

from packaging.requirements import Requirement

ROOT_DISTRIBUTION = "qplanck"
ALLOWED_LICENSES = frozenset(
    {
        "0BSD",
        "Apache-2.0",
        "BSD-3-Clause",
        "CC0-1.0",
        "MIT",
        "PSF-2.0",
        "Python-2.0",
        "Unicode-3.0",
        "Zlib",
    }
)
SPDX_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*")
SPDX_OPERATORS = frozenset({"AND", "OR", "WITH"})


def _license_expression(distribution: metadata.Distribution) -> str:
    expression = distribution.metadata.get("License-Expression")
    if expression:
        return expression.strip()
    legacy = distribution.metadata.get("License")
    if legacy and legacy.strip().upper() != "UNKNOWN":
        return legacy.strip()
    raise RuntimeError(f"{distribution.metadata['Name']} has no usable license expression.")


def _validate_license(name: str, expression: str) -> None:
    tokens = {
        token
        for token in SPDX_TOKEN.findall(expression)
        if token.upper() not in SPDX_OPERATORS
    }
    unsupported = sorted(tokens - ALLOWED_LICENSES)
    if not tokens or unsupported:
        raise RuntimeError(
            f"{name} uses license expression {expression!r}; unsupported tokens: {unsupported}."
        )


def runtime_closure(root: str = ROOT_DISTRIBUTION) -> tuple[metadata.Distribution, ...]:
    pending = [root]
    found: dict[str, metadata.Distribution] = {}
    while pending:
        requested = pending.pop()
        distribution = metadata.distribution(requested)
        canonical = distribution.metadata["Name"].lower().replace("_", "-")
        if canonical in found:
            continue
        found[canonical] = distribution
        for raw_requirement in distribution.requires or ():
            requirement = Requirement(raw_requirement)
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            dependency = metadata.distribution(requirement.name)
            if requirement.specifier and dependency.version not in requirement.specifier:
                raise RuntimeError(
                    f"Installed {requirement.name}=={dependency.version} does not satisfy "
                    f"{requirement.specifier}."
                )
            pending.append(requirement.name)
    return tuple(found[name] for name in sorted(found))


def main() -> int:
    for distribution in runtime_closure():
        name = distribution.metadata["Name"]
        expression = _license_expression(distribution)
        _validate_license(name, expression)
        print(f"{name}=={distribution.version}: {expression}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
