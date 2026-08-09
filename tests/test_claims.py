import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_claim_registry_is_complete_and_machine_readable() -> None:
    registry = json.loads((ROOT / "docs" / "claims.json").read_text(encoding="utf-8"))

    assert registry["schema_version"] == "qplanck.claims.v0.1"
    claims = {item["id"]: item for item in registry["claims"]}
    assert set(claims) == {
        "planner-vertical-slice",
        "planner-v0.1-go",
        "native-compiler",
        "target-routing",
        "braket-offline",
        "braket-hardware",
        "competitive-performance",
        "browser-support",
    }
    assert claims["planner-vertical-slice"]["status"] == "offline-verified"
    planner_wording = claims["planner-vertical-slice"]["allowed_wording"].casefold()
    assert "one versioned synthetic fixture" in planner_wording
    assert "15-pair development cohort" in planner_wording
    assert "45 offline compiler-reexecution replays" in planner_wording
    assert claims["planner-v0.1-go"]["status"] == "gated"
    assert claims["planner-v0.1-go"]["allowed_wording"] is None
    assert claims["braket-hardware"]["status"] == "gated"
    assert claims["braket-hardware"]["allowed_wording"] is None
    assert claims["competitive-performance"]["status"] == "gated"
    assert claims["competitive-performance"]["allowed_wording"] is None
    assert claims["browser-support"]["status"] == "unsupported"
    assert "does not support Pyodide or WebAssembly" in claims["browser-support"]["allowed_wording"]


def test_public_entrypoints_do_not_make_forbidden_blanket_claims() -> None:
    public_text = "\n".join(
        path.read_text(encoding="utf-8").casefold()
        for path in (ROOT / "README.md", ROOT / "docs" / "index.md", ROOT / "index.md")
    )

    assert "qcore beats qiskit" not in public_text
    assert "qcore beats all" not in public_text
    assert "universal qir support" not in public_text


def test_native_release_contract_has_no_browser_or_python_only_build() -> None:
    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["build-system"]["build-backend"] == "maturin"
    assert project["tool"]["maturin"]["module-name"] == "qplanck._qplanck_native"
    assert "abi3-py311" in cargo["dependencies"]["pyo3"]["features"]
    assert "wasm" not in cargo.get("features", {})
    assert "wasm-bindgen" not in cargo.get("dependencies", {})
