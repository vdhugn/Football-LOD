from rdflib import Literal, URIRef
from rdflib.namespace import XSD

from common import (BuildCtx, TurtleWriter, Uris, clean, expand_seasons, hash_id, iri,
                    lit, parse_date, parse_decimal, parse_int, parse_net_transfer,
                    slug, t_int)
from helpers import FB, R, load_ttl


def test_clean():
    assert clean("  Opole  ") == "Opole"
    assert clean("") is None and clean("   ") is None and clean(None) is None
    assert clean("a\x00b") == "ab"


def test_parse_date():
    assert parse_date("1978-06-09 00:00:00") == "1978-06-09"
    assert parse_date("2019-07-01") == "2019-07-01"
    assert parse_date("") is None and parse_date("garbage") is None


def test_parse_numbers():
    assert parse_int("90") == "90" and parse_int("2.0") == "2"
    assert parse_int("") is None and parse_int("x") is None and parse_int("NaN") is None
    assert parse_decimal("700000.000") == "700000"
    assert parse_decimal("0.000") == "0"
    assert parse_decimal("27.1") == "27.1"
    assert parse_decimal("abc") is None


def test_parse_net_transfer():
    assert parse_net_transfer("+€5.90m") == "5900000"
    assert parse_net_transfer("€-25.00m") == "-25000000"
    assert parse_net_transfer("€0") == "0"
    assert parse_net_transfer("+€350k") == "350000"
    assert parse_net_transfer("-") is None and parse_net_transfer("") is None


def test_slug_and_hash_and_iri():
    assert slug(" Emirates Stadium ") == "Emirates_Stadium"
    assert slug("") is None
    assert hash_id("1", "2") == hash_id("1", "2") != hash_id("2", "1")
    assert len(hash_id("x")) == 16
    assert iri("https://a.b/c") == "<https://a.b/c>"
    assert iri("has space") is None and iri("") is None


def test_expand_seasons():
    assert expand_seasons({"from": 2012, "to": 2014}) == [2012, 2013, 2014]
    assert expand_seasons([2005, "2009"]) == [2005, 2009]


def test_uris(cfg):
    u = Uris(cfg)
    assert u.res("player", "10") == f"<{R}player/10>"
    assert u.res("player", "") is None and u.res("player", None) is None
    assert u.res("stadium", "Allianz Arena") == f"<{R}stadium/Allianz%20Arena>"
    assert u.team("club", "5") == f"<{R}club/5>"
    assert u.team("national", "5") == f"<{R}national-team/5>"
    assert u.team("club", "") is None


def test_writer_round_trips_awkward_literals(tmp_path):
    tricky = 'O"Brien \\ back\nnewline\ttab Türkiye'
    path = tmp_path / "t.ttl"
    with TurtleWriter(path, FB) as w:
        w.node(f"<{R}player/1>", ("a", "fb:Player"), ("rdfs:label", lit(tricky, "und")),
               ("fb:heightCm", t_int("178")), ("fb:agent", None), ("fb:x", None))
        w.node(f"<{R}player/2>", ("fb:agent", None))  # nothing to write
    g = load_ttl(path)
    assert w.count == 3
    assert (URIRef(f"{R}player/1"), URIRef("http://www.w3.org/2000/01/rdf-schema#label"),
            Literal(tricky, lang="und")) in g
    assert (URIRef(f"{R}player/1"), URIRef(FB + "heightCm"), Literal("178", datatype=XSD.integer)) in g
    assert len(g) == 3


def test_writer_accepts_list_objects(tmp_path):
    path = tmp_path / "t.ttl"
    with TurtleWriter(path, FB) as w:
        w.node(f"<{R}position/Attack>", ("a", ["fb:Position", "skos:Concept"]))
    assert len(load_ttl(path)) == 2


def test_once_and_named_node(cfg, tmp_path):
    from common import named_node
    ctx = BuildCtx(cfg, Uris(cfg), scope=None, data_dir=tmp_path, out_dir=tmp_path)
    path = tmp_path / "n.ttl"
    with TurtleWriter(path, FB) as w:
        a = named_node(ctx, w, "stadium", "fb:Stadium", " Emirates Stadium ")
        b = named_node(ctx, w, "stadium", "fb:Stadium", "Emirates Stadium")
        assert named_node(ctx, w, "stadium", "fb:Stadium", "") is None
    assert a == b == f"<{R}stadium/Emirates_Stadium>"
    assert len(load_ttl(path)) == 2
