"""Provider-identifier redaction for portable QPlanck artifacts."""

from __future__ import annotations

import hashlib
import re

_SAFE_ARN_COMPONENT = re.compile(r"^[A-Za-z0-9._/-]+$")


def redacted_arn_identity(arn: str) -> str:
    """Return a stable, useful ARN identity without its AWS account field.

    Braket task resource IDs remain available for correlating protected smoke
    evidence with an operator-held ARN. Region and account fields are always
    replaced, so the result is not a usable provider resource locator.
    """

    value = arn.strip()
    parts = value.split(":", 5)
    if (
        len(parts) == 6
        and parts[0] == "arn"
        and all(_SAFE_ARN_COMPONENT.fullmatch(part) for part in (parts[1], parts[2]))
        and _SAFE_ARN_COMPONENT.fullmatch(parts[5])
    ):
        resource = parts[5]
        account = parts[4]
        if account:
            resource = resource.replace(account, "[REDACTED]")
        return f"arn:{parts[1]}:{parts[2]}:[REDACTED]:[REDACTED]:{resource}"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"aws-resource:sha256:{digest}"


__all__ = ["redacted_arn_identity"]
