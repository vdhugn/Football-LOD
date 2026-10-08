from pathlib import Path

from pyshacl import validate
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF

from build_rdf import run
from helpers import FB, R

ROOT = Path(__file__).resolve().parents[1]


def load_all(out):
    g = Graph()
    for f in sorted((out / "data").glob("*.ttl")):
        g.parse(str(f), format="turtle")
    return g


def shacl(data, ont):
    shapes = Graph().parse(str(ROOT / "shapes" / "football-shapes.ttl"), format="turtle")
    conforms, _, text = validate(data, shacl_graph=shapes, ont_graph=ont, inference=None)
    return conforms, text


def test_fixture_data_conforms(cfg, data_dir, tmp_path):
    from scope import select_scope
    out = tmp_path / "out"
    run(cfg, select_scope(cfg, data_dir), data_dir, out)
    ont = Graph().parse(str(ROOT / "ontology" / "football.ttl"), format="turtle")
    conforms, text = shacl(load_all(out), ont)
    assert conforms, text


def test_transfer_without_destination_club_violates(cfg, data_dir, tmp_path):
    from common import hash_id
    from scope import select_scope
    out = tmp_path / "out"
    run(cfg, select_scope(cfg, data_dir), data_dir, out)
    ont = Graph().parse(str(ROOT / "ontology" / "football.ttl"), format="turtle")
    g = load_all(out)
    g.remove((URIRef(f"{R}transfer/{hash_id('10', '2023-01-01', '11', '148')}"), URIRef(FB + "toClub"), None))
    conforms, text = shacl(g, ont)
    assert not conforms and "toClub" in text


def test_valuation_pointing_to_unknown_player_violates(cfg, data_dir, tmp_path):
    from scope import select_scope
    out = tmp_path / "out"
    run(cfg, select_scope(cfg, data_dir), data_dir, out)
    ont = Graph().parse(str(ROOT / "ontology" / "football.ttl"), format="turtle")
    g = load_all(out)
    g.set((URIRef(f"{R}valuation/10-2023-06-01"), URIRef(FB + "valuationOf"), URIRef(f"{R}player/does-not-exist")))
    conforms, _ = shacl(g, ont)
    assert not conforms
