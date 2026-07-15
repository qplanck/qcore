# Publishing `qplanck`

QCore is the product name. The Python distribution, import package, and command
line program are named `qplanck`; the unrelated `qcore` distribution must not be
used for this project.

## Release policy

- PyPI files and version numbers are immutable. Increment the version for every
  retry after an upload.
- TestPyPI is the first publication target for every new release workflow.
- Production publication happens only from a published GitHub release.
- GitHub Actions uses PyPI trusted publishing (OIDC); the repository does not
  store a long-lived PyPI API token.
- The wheel and source distribution must come from the same workflow artifact.

The workflow is [`.github/workflows/publish.yml`](../.github/workflows/publish.yml).

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

If the organization or repository name differs at publication time, use the
actual GitHub identity. Configure the GitHub `pypi` environment with required
reviewers so a release cannot publish without human approval.

For a first project upload, PyPI's pending-publisher flow can reserve the project
for this exact workflow. A missing project page does not guarantee that a name is
available.

## Pre-release verification

Run from a clean checkout with Python 3.13 or 3.14:

```bash
python -m venv .venv-release
source .venv-release/bin/activate
python -m pip install --upgrade pip ".[dev,qiskit,qir-validation]" build twine
python -m build
python -m twine check --strict dist/*
```

Install the wheel itself rather than the source tree:

```bash
python -m venv /tmp/qplanck-wheel-test
/tmp/qplanck-wheel-test/bin/pip install dist/qplanck-*.whl
/tmp/qplanck-wheel-test/bin/qplanck doctor
```

Also run the complete repository checks:

```bash
ruff check .
ruff format --check .
mypy src/qplanck
pytest --cov
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
  qplanck==0.2.0a1
/tmp/qplanck-testpypi/bin/qplanck doctor
```

The extra production index supplies dependencies such as NumPy that may not be
present on TestPyPI. It is appropriate only for this isolated installation test,
not as an application dependency policy.

## Production release

1. Confirm the release commit passes CI and TestPyPI installation.
2. Confirm `pyproject.toml` and `qplanck.__version__` contain the same unused
   version.
3. Move that version's [changelog](../CHANGELOG.md) entry from `Unreleased` to the
   release date.
4. Create a GitHub release from that commit and publish it.
5. Approve the protected `pypi` environment.
6. Verify the project page, wheel installation, CLI, imports, and README rendering.

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
