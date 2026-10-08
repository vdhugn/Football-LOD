import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from helpers import write_mini  # noqa: E402


@pytest.fixture
def cfg():
    return {
        "ontology_base": "https://vdhugn.github.io/Football-LOD/ontology#",
        "resource_base": "https://vdhugn.github.io/Football-LOD/resource/",
        "scope": {"leagues": ["GB1"], "season": 2025},
    }


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "datasets"
    d.mkdir()
    write_mini(d)
    return d


@pytest.fixture
def ctx(cfg, data_dir, tmp_path):
    from common import BuildCtx, Uris
    from scope import select_scope

    out = tmp_path / "out"
    out.mkdir()
    return BuildCtx(cfg, Uris(cfg), select_scope(cfg, data_dir), data_dir, out)
