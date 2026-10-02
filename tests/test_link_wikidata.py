import json

from rdflib import URIRef
from rdflib.namespace import OWL, SKOS

import link_wikidata as lw
from common import Uris
from helpers import R, load_ttl

WD = "http://www.wikidata.org/entity/"


def canned(rows):
    def fetch(query):
        bindings = [{k: {"type": "literal", "value": v} for k, v in r.items()} for r in rows]
        return {"results": {"bindings": bindings}}
    return fetch


def test_tm_query_contains_property_and_values():
    q = lw.tm_query("P2446", ["10", "26"])
    assert "wdt:P2446" in q and '"10"' in q and '"26"' in q
    assert "wdt:P115" not in q
    assert "wdt:P115" in lw.tm_query("P7223", ["1"], with_venue=True)


def test_cached_query_is_offline_on_second_call(tmp_path):
    calls = []

    def fetch(q):
        calls.append(q)
        return {"results": {"bindings": []}}

    lw.cached_query(tmp_path, "k", "SELECT 1", fetch, pause=0)
    lw.cached_query(tmp_path, "k", "SELECT 1", lambda q: (_ for _ in ()).throw(AssertionError("network!")), pause=0)
    assert len(calls) == 1


def test_fetch_rows_batches_and_dedupes(tmp_path):
    seen = []

    def fetch(q):
        seen.append(q)
        return {"results": {"bindings": [
            {"item": {"value": WD + "Q1"}, "tm": {"value": "10"}},
            {"item": {"value": WD + "Q1"}, "tm": {"value": "10"}},      # duplicate row
        ]}}

    rows = lw.fetch_rows("P2446", ["10", "11", "12"], tmp_path, "player", fetch, batch=2, pause=0)
    assert len(seen) == 2                      # 3 ids, batch size 2
    assert len(rows) == 1 and rows[0]["item"] == WD + "Q1"


def test_dbpedia_uri():
    assert lw.dbpedia_uri("https://en.wikipedia.org/wiki/Bukayo_Saka") == "http://dbpedia.org/resource/Bukayo_Saka"
    assert lw.dbpedia_uri("https://en.wikipedia.org/wiki/Real_Madrid_CF") == "http://dbpedia.org/resource/Real_Madrid_CF"
    assert lw.dbpedia_uri(None) is None
    assert lw.dbpedia_uri("https://de.wikipedia.org/wiki/X") is None


def test_write_links(cfg, tmp_path):
    uris = Uris(cfg)
    kinds = {
        "player": [{"item": WD + "Q1", "tm": "10", "article": "https://en.wikipedia.org/wiki/Bukayo_Saka"}],
        "competition": [{"item": WD + "Q9", "tm": "GB1"}],
    }
    counts = lw.write_links(tmp_path, uris, kinds)
    g = load_ttl(tmp_path / "wikidata.ttl")
    assert (URIRef(f"{R}player/10"), OWL.sameAs, URIRef(WD + "Q1")) in g
    assert (URIRef(f"{R}competition/GB1"), OWL.sameAs, URIRef(WD + "Q9")) in g
    d = load_ttl(tmp_path / "dbpedia.ttl")
    assert (URIRef(f"{R}player/10"), OWL.sameAs, URIRef("http://dbpedia.org/resource/Bukayo_Saka")) in d
    assert counts == {"player": 1, "competition": 1}


def test_stadium_links_use_closematch_and_normalised_names(cfg, tmp_path):
    uris = Uris(cfg)
    club_rows = [{"item": WD + "Q5", "tm": "11", "venue": WD + "Q99", "venueLabel": "Emirates Stadium"}]
    club_stadium = {"11": "emirates stadium"}                  # case-folded name from clubs.csv
    n = lw.write_stadium_links(tmp_path, uris, club_rows, {"11": "Emirates Stadium"})
    g = load_ttl(tmp_path / "stadiums.ttl")
    assert (URIRef(f"{R}stadium/Emirates_Stadium"), SKOS.closeMatch, URIRef(WD + "Q99")) in g
    assert n == 1
    # a venue whose label differs is not linked
    club_rows2 = [{"item": WD + "Q5", "tm": "11", "venue": WD + "Q98", "venueLabel": "Highbury"}]
    assert lw.write_stadium_links(tmp_path, uris, club_rows2, {"11": "Emirates Stadium"}) == 0


def test_country_rows_and_geonames(cfg, tmp_path):
    fetch = canned([{"name": "England", "item": WD + "Q21", "geonames": "6269131"}])
    rows = lw.country_rows(["England", "Atlantis"], tmp_path, fetch, pause=0)
    assert rows == [{"name": "England", "item": WD + "Q21", "geonames": "6269131"}]
    uris = Uris(cfg)
    n = lw.write_country_links(tmp_path, rows, {"England": f"<{R}country/189>"})
    g = load_ttl(tmp_path / "geonames.ttl")
    assert (URIRef(f"{R}country/189"), OWL.sameAs, URIRef("https://sws.geonames.org/6269131/")) in g
    w = load_ttl(tmp_path / "wikidata-countries.ttl")
    assert (URIRef(f"{R}country/189"), OWL.sameAs, URIRef(WD + "Q21")) in w
    assert n == 1


def test_report(tmp_path):
    lw.write_report(tmp_path, {"player": (100, 90), "club": (10, 0)})
    rep = json.loads((tmp_path / "report.json").read_text())
    assert rep["player"] == {"total": 100, "linked": 90, "rate": 0.9}
    assert rep["club"]["rate"] == 0.0


def test_country_rows_dedupes_items_matched_through_several_types(tmp_path):
    row = {"name": "Spain", "item": WD + "Q29", "geonames": "2510769"}
    rows = lw.country_rows(["Spain"], tmp_path, canned([row, row]), pause=0)   # item has two P31 types
    assert rows == [row]
