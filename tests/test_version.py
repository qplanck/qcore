import importlib.metadata

import qplanck


def test_runtime_and_distribution_versions_match() -> None:
    assert qplanck.__version__ == importlib.metadata.version("qplanck")
