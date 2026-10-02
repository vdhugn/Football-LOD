import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ["src", "ontology", "shapes", "queries", "tests", "scripts", "docker", "config.json", "Makefile"]


def test_no_placeholder_namespace_left():
    me = Path(__file__).resolve()
    hits = []
    for entry in SCAN:
        path = ROOT / entry
        files = [path] if path.is_file() else (p for p in path.rglob("*") if p.is_file())
        for f in files:
            if "__pycache__" in f.parts or f.resolve() == me:
                continue
            if "example.org" in f.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(f.relative_to(ROOT)))
    assert hits == []


def test_config_uses_the_real_namespace():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    assert cfg["resource_base"] == "https://vdhugn.github.io/Football-LOD/resource/"
    assert cfg["ontology_base"] == "https://vdhugn.github.io/Football-LOD/ontology#"
