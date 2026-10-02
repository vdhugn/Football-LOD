from pathlib import Path

from build_rdf import run
from helpers import load_ttl
from validate import check_vocabulary

ONT = Path(__file__).resolve().parents[1] / "ontology" / "football.ttl"
EXPECTED = {"reference.ttl", "clubs.ttl", "players.ttl", "matches.ttl",
            "appearances.ttl", "events.ttl", "transfers.ttl", "valuations.ttl"}


def test_run_writes_all_files_that_parse(cfg, data_dir, tmp_path):
    from scope import select_scope
    out = tmp_path / "out"
    totals = run(cfg, select_scope(cfg, data_dir), data_dir, out)
    assert set(totals) == EXPECTED
    for name in EXPECTED:
        assert (out / "data" / name).exists()
        assert len(load_ttl(out / "data" / name)) > 0


def test_every_fb_term_used_is_defined_in_the_ontology(cfg, data_dir, tmp_path):
    from scope import select_scope
    out = tmp_path / "out"
    run(cfg, select_scope(cfg, data_dir), data_dir, out)
    files = sorted((out / "data").glob("*.ttl"))
    assert check_vocabulary(ONT, files, cfg["ontology_base"]) == set()


def test_vocabulary_check_detects_unknown_term(tmp_path):
    f = tmp_path / "x.ttl"
    f.write_text("<http://x/a> fb:notDefinedAnywhere 1 .\n", encoding="utf-8")
    assert check_vocabulary(ONT, [f], "https://vdhugn.github.io/Football-LOD/ontology#") == {"notDefinedAnywhere"}


def test_output_is_deterministic(cfg, data_dir, tmp_path):
    from scope import select_scope
    scope = select_scope(cfg, data_dir)
    run(cfg, scope, data_dir, tmp_path / "a")
    run(cfg, select_scope(cfg, data_dir), data_dir, tmp_path / "b")
    for name in EXPECTED:
        assert (tmp_path / "a" / "data" / name).read_bytes() == (tmp_path / "b" / "data" / name).read_bytes()
