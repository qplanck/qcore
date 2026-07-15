import json

import pytest

from qplanck.errors import InteropError
from qplanck.interop import (
    ConversionResult,
    InteropIssue,
    InteropIssueKind,
    LossReport,
)


def test_loss_report_is_deterministic_and_distinguishes_warnings() -> None:
    loss = InteropIssue(
        code="QCORE-INTEROP-METADATA-DROPPED",
        kind=InteropIssueKind.LOSS,
        message="Metadata is not represented.",
        path="operations[0].metadata",
    )
    warning = InteropIssue(
        code="QCORE-INTEROP-SOURCE-TEXT-NORMALIZED",
        kind=InteropIssueKind.WARNING,
        message="Formatting is normalized.",
    )
    report = LossReport(
        "qplanck.ir.v0.1",
        "openqasm-3.0-subset",
        preserved=("gates", "measurements", "gates"),
        issues=(loss, warning),
    )

    assert report.preserved == ("gates", "measurements")
    assert report.losses == (loss,)
    assert report.warnings == (warning,)
    assert not report.is_lossless
    assert json.loads(report.to_json())["issues"][0]["code"] == warning.code

    with pytest.raises(InteropError, match="QCORE-INTEROP-METADATA-DROPPED"):
        report.require_lossless()


def test_conversion_result_pairs_value_and_lossless_report() -> None:
    report = LossReport("qplanck.ir.v0.1", "qir-base-profile", preserved=("gates",))
    result = ConversionResult("module text", report)

    assert result.value == "module text"
    assert result.report.is_lossless
    result.report.require_lossless()


def test_interop_issue_rejects_unstable_code_namespace() -> None:
    with pytest.raises(ValueError, match="QCORE-INTEROP"):
        InteropIssue("METADATA-DROPPED", InteropIssueKind.LOSS, "Metadata is lost.")
