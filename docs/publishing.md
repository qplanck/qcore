# Publishing `qplanck` and `qplanck-braket`

QCore is the product name. The Python distribution, import package, and command
line program are named `qplanck`; the unrelated `qcore` distribution must not be
used for this project. The Amazon Braket adapter is a separately versioned
distribution named `qplanck-braket`.

## Release policy

- PyPI files and version numbers are immutable. Increment the version for every
  retry after an upload.
- TestPyPI is the first publication target for every new release workflow.
- Production publication happens only from a published GitHub release.
- GitHub Actions uses PyPI trusted publishing (OIDC); the repository does not
  store a long-lived PyPI API token.
- The core wheel and source distribution must come from the same workflow run.
- `qplanck 0.3` is native-required. A pure-Python wheel must never be published.
- `qplanck-braket` production publication is blocked until its protected live
  smoke records one successful task; TestPyPI rehearsal is allowed beforehand.

The core workflow is
[`publish.yml`](../.github/workflows/publish.yml). The provider adapter has a
separate workflow and publishing identity so a provider gate cannot block or
weaken the core release.

## One-time project setup

An owner must create matching trusted-publisher entries on
[TestPyPI](https://test.pypi.org/manage/account/publishing/) and
[PyPI](https://pypi.org/manage/account/publishing/) with:

| Field | TestPyPI | PyPI |
|---|---|---|
| PyPI project | `qplanck` | `qplanck` |
| GitHub owner | `qplanck` | `qplanck` |
| Repository | `qcore` | `qcore` |
| Workflow | `publish.yml` | `publish.yml` |
| Environment | `testpypi` | `pypi` |

Create separate pending/trusted publishers for `qplanck-braket` only when its
workflow is ready. Do not give one distribution permission to publish the other.

If the organization or repository name differs at publication time, use the
actual GitHub identity. Configure the GitHub `pypi` environment with required
reviewers so a release cannot publish without human approval.

For a first project upload, PyPI's pending-publisher flow can reserve the project
for this exact workflow. A missing project page does not guarantee that a name is
available.

## Pre-release verification

Run from a clean checkout with CPython 3.11-3.14 and the pinned Rust toolchain:

```bash
rustup show
python -m venv .venv-release
source .venv-release/bin/activate
python -m pip install --upgrade pip maturin==1.8.2 twine
python -m pip install -e ".[dev,qiskit,qir-validation]"
cargo fmt --all --check
cargo clippy --locked --all-targets --all-features -- -D warnings
cargo test --locked --all-features
cargo check --locked --no-default-features
cargo deny --all-features check advisories bans licenses sources
maturin build --release --locked --out dist
maturin sdist --out dist
python -m twine check --strict dist/*
```

The release workflow builds `abi3-py311` wheels for manylinux and musllinux on
x86_64/aarch64, macOS on x86_64/arm64, and Windows x64. CPython 3.11-3.14 is the
supported interpreter range. Free-threaded CPython, PyPy, Windows ARM64, and
WebAssembly are not release targets. A source installation requires Rust 1.85.0
and the locked Cargo dependency graph.

The release workflow does not build WebAssembly or publish a JavaScript binding,
browser runtime, or npm artifact.

Install the wheel itself rather than the source tree:

```bash
python -m venv /tmp/qplanck-wheel-test
/tmp/qplanck-wheel-test/bin/pip install dist/qplanck-0.3.0a1-*.whl
/tmp/qplanck-wheel-test/bin/qplanck doctor
/tmp/qplanck-wheel-test/bin/python -c \
  "from qplanck import Circuit; Circuit(2).h(0).cx(0, 1).compile()"
```

Also run the complete repository checks:

```bash
ruff check .
ruff format --check .
mypy src/qplanck
pytest --cov
```

Run the adapter checks independently on CPython 3.11-3.13:

```bash
python -m pip install -e "packages/qplanck-braket[dev]"
ruff check packages/qplanck-braket
mypy packages/qplanck-braket/src/qplanck_braket
pytest packages/qplanck-braket/tests
python -m build packages/qplanck-braket
python -m twine check --strict packages/qplanck-braket/dist/*
```

## TestPyPI rehearsal

1. Open the `Publish Python distribution` action in GitHub.
2. Run the workflow manually from the exact release commit.
3. Approve the `testpypi` environment if protection is enabled.
4. Install the uploaded version in a new environment:

```bash
python -m venv /tmp/qplanck-testpypi
/tmp/qplanck-testpypi/bin/pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  qplanck==0.3.0a1
/tmp/qplanck-testpypi/bin/qplanck doctor
```

The extra production index supplies dependencies such as NumPy that may not be
present on TestPyPI. It is appropriate only for this isolated installation test,
not as an application dependency policy.

Repeat this rehearsal for `qplanck-braket==0.1.0a1` only after `qplanck` is
available on TestPyPI. This is an artifact/install check, not authorization for a
live Braket task or production adapter release.

## Production release

1. Confirm the release commit passes CI and TestPyPI installation.
2. Confirm `pyproject.toml` and `qplanck.__version__` contain the same unused
   version.
3. Move that version's [changelog](../CHANGELOG.md) entry from `Unreleased` to the
   release date.
4. Create a GitHub release from that commit and publish it.
5. Confirm the native correctness, wheel, and benchmark reports. Keep all named
   superiority claims gated unless every threshold passes.
6. Approve the protected `pypi` environment.
7. Verify the project page, wheel installation, native compile/QIR smoke, CLI,
   imports, and README rendering on each supported platform family.

For `qplanck-braket`, additionally require the manual live workflow to preflight
IAM, device availability, cost (at most $10), payload, shots, and snapshot
identity; submit exactly one task with no retry; record the redacted ARN, status,
counts, and snapshot hashes; and make no fidelity claim. With no AWS credentials
available, production publication remains blocked by design.

Do not rerun a failed production upload with the same version if any file reached
PyPI. Diagnose the failure, increment the version, rebuild from a clean checkout,
and repeat TestPyPI verification.

## Manual emergency path

Trusted publishing is the normal path. If GitHub Actions is unavailable and the
release owner explicitly authorizes a manual upload, use a scoped token and
Twine:

```bash
python -m twine upload dist/*
```

Use `__token__` as the username and the complete `pypi-...` token as the
password. Never place a token in this repository, shell history, command
arguments, or an unprotected CI secret.
