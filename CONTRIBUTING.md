# Contributing to QCore

Thanks for helping build QCore. The project is early, so the most valuable
contributions are clear tests, examples, documentation, and tightly scoped
improvements to the core circuit/trace semantics.

## Development Setup

```bash
python -m pip install -e ".[dev]"
pre-commit install
pytest
```

For Qiskit adapter work:

```bash
python -m pip install -e ".[dev,qiskit]"
pytest
```

## Pull Request Expectations

- Keep changes focused.
- Add tests for behavior changes.
- Run `ruff check .`, `mypy src/qplanck`, and `pytest`.
- Update docs or examples when public behavior changes.
- Preserve the v0.1 supported subset unless an issue or RFC expands it.

## Certificate of Origin

QCore uses the Developer Certificate of Origin instead of a CLA. Sign commits
with:

```bash
git commit -s
```

The sign-off certifies that you have the right to submit the contribution under
the project license. See [DCO.md](DCO.md).

## Good First Areas

- Documentation improvements
- Additional circuit examples
- Golden tests for OpenQASM 3 import/export
- Error-message clarity
- Visual trace schema examples
