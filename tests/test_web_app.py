import json

import pytest
from rdflib import Graph

from footballweb import create_app
from footballweb.fuseki import FusekiError, FusekiFailure, FusekiUnavailable
from helpers import FB, R

PLAYER_TTL = f"""@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<{R}player/10> rdfs:label "Bukayo Saka"@und .
"""
LABEL = "http://www.w3.org/2000/01/rdf-schema#label"


def result(vars_, rows):
    return {"head": {"vars": vars_}, "results": {"bindings": rows}}


class Fake:
    def __init__(self, routes=None, ask=True, construct=PLAYER_TTL, error=None):
        self.routes, self._ask, self._construct, self.error, self.queries = routes or {}, ask, construct, error, []

    def _maybe_fail(self):
        if self.error:
            raise self.error

    def select(self, q):
        self.queries.append(q)
        self._maybe_fail()
        for marker, data in self.routes.items():
            if marker in q:
                return data
        return result([], [])

    def ask(self, q):
        self.queries.append(q)
        self._maybe_fail()
        return self._ask

    def construct(self, q):
        self.queries.append(q)
        self._maybe_fail()
        return self._construct


@pytest.fixture
def cfg():
    return {"ontology_base": FB, "resource_base": R}


def client_for(cfg, fake):
    app = create_app(cfg=cfg, client=fake)
    app.testing = True
    return app.test_client()


# ---------- content negotiation ----------

@pytest.mark.parametrize("accept,target", [
    ("text/html", "/page/player/10"),
    ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "/page/player/10"),
    ("*/*", "/page/player/10"),
    (None, "/page/player/10"),
    ("text/turtle", "/data/player/10.ttl"),
    ("application/ld+json", "/data/player/10.jsonld"),
    ("application/rdf+xml", "/data/player/10.rdf"),
    ("application/n-triples", "/data/player/10.nt"),
])
def test_resource_redirects_by_accept_header(cfg, accept, target):
    c = client_for(cfg, Fake())
    r = c.get("/resource/player/10", headers={"Accept": accept} if accept else {})
    assert r.status_code == 303 and r.headers["Location"].endswith(target)


def test_resource_unknown_or_invalid_is_404(cfg):
    assert client_for(cfg, Fake(ask=False)).get("/resource/player/999").status_code == 404
    assert client_for(cfg, Fake()).get("/resource/Bad_Kind/1").status_code == 404
    assert client_for(cfg, Fake()).get("/page/Bad_Kind/1").status_code == 404
    assert client_for(cfg, Fake()).get("/data/Bad_Kind/1.ttl").status_code == 404


def test_ids_with_special_characters_round_trip(cfg):
    fake = Fake()
    c = client_for(cfg, fake)
    r = c.get("/resource/stadium/Allianz%20Arena", headers={"Accept": "text/turtle"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/data/stadium/Allianz%20Arena.ttl")
    c.get("/data/stadium/Allianz%20Arena.ttl")
    assert f"<{R}stadium/Allianz%20Arena>" in fake.queries[-1]
    r = c.get('/resource/referee/Mr_%22Q%22', headers={"Accept": "text/turtle"})
    assert r.status_code == 303
    c.get('/data/referee/Mr_%22Q%22.ttl')
    assert f"<{R}referee/Mr_%22Q%22>" in fake.queries[-1]


# ---------- data documents ----------

def test_data_in_every_format(cfg):
    c = client_for(cfg, Fake())
    ttl = c.get("/data/player/10.ttl")
    assert ttl.status_code == 200 and ttl.mimetype == "text/turtle" and b"Bukayo Saka" in ttl.data
    js = c.get("/data/player/10.jsonld")
    assert js.mimetype == "application/ld+json" and json.loads(js.data)
    assert b"rdf:RDF" in c.get("/data/player/10.rdf").data
    nt = c.get("/data/player/10.nt")
    assert nt.mimetype == "application/n-triples" and nt.data.strip().endswith(b".")
    for body in (ttl.data, js.data, nt.data):
        g = Graph()
        g.parse(data=body.decode(), format={"ttl": "turtle"}.get("ttl") if body is ttl.data else ("json-ld" if body is js.data else "nt"))
        assert len(g) == 1


def test_data_unknown_extension_or_empty_graph_is_404(cfg):
    assert client_for(cfg, Fake()).get("/data/player/10.pdf").status_code == 404
    assert client_for(cfg, Fake()).get("/data/player/10").status_code == 404
    assert client_for(cfg, Fake(construct="")).get("/data/player/10.ttl").status_code == 404


# ---------- HTML pages ----------

def test_entity_page_renders_data_and_links(cfg):
    rows = [
        {"p": {"type": "uri", "value": LABEL}, "o": {"type": "literal", "value": "Bukayo Saka", "xml:lang": "und"}},
        {"p": {"type": "uri", "value": FB + "playsFor"}, "o": {"type": "uri", "value": f"{R}club/11"},
         "ol": {"type": "literal", "value": "Arsenal FC"}},
        {"p": {"type": "uri", "value": "http://www.w3.org/2002/07/owl#sameAs"},
         "o": {"type": "uri", "value": "http://www.wikidata.org/entity/Q1"}},
    ]
    fake = Fake({"GROUP BY ?p ?o": result(["p", "o", "ol"], rows),
                 "fb:transferOf": result(["date", "from", "fl", "to", "tl", "fee"], [{
                     "date": {"type": "literal", "value": "2023-01-01"},
                     "from": {"type": "uri", "value": f"{R}club/11"}, "fl": {"type": "literal", "value": "Arsenal FC"},
                     "to": {"type": "uri", "value": f"{R}club/148"}, "tl": {"type": "literal", "value": "Spurs"},
                     "fee": {"type": "literal", "value": "5000000.0"}}])})
    html = client_for(cfg, fake).get("/page/player/10").get_data(as_text=True)
    assert "Bukayo Saka" in html and f"{R}player/10" in html
    assert 'href="/page/club/11"' in html and "Arsenal FC" in html
    assert 'href="http://www.wikidata.org/entity/Q1"' in html
    assert "Transfers" in html and "5,000,000" in html and "2023-01-01" in html
    assert "/data/player/10.ttl" in html and "/data/player/10.jsonld" in html
    assert "<script>" not in html.split("</head>")[1].split("<script src")[0]


def test_entity_page_escapes_hostile_values(cfg):
    rows = [{"p": {"type": "uri", "value": LABEL}, "o": {"type": "literal", "value": "<script>alert(1)</script>"}}]
    html = client_for(cfg, Fake({"GROUP BY ?p ?o": result(["p", "o", "ol"], rows)})).get("/page/player/10").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_unknown_entity_page_is_404_html(cfg):
    r = client_for(cfg, Fake()).get("/page/player/999")
    assert r.status_code == 404 and "text/html" in r.content_type


def test_search_page(cfg):
    rows = [{"s": {"type": "uri", "value": f"{R}player/10"}, "label": {"type": "literal", "value": "Bukayo Saka"},
             "type": {"type": "uri", "value": FB + "Player"}}]
    c = client_for(cfg, Fake({"?label": result(["s", "label", "type"], rows)}))
    ok = c.get("/search?q=saka")
    assert ok.status_code == 200 and 'href="/page/player/10"' in ok.get_data(as_text=True)
    assert c.get("/search?q=a").status_code == 400
    assert c.get("/search?q=" + "x" * 81).status_code == 400
    assert c.get("/search").status_code == 200                     # empty form
    assert c.get("/search?q=none-here").status_code == 200


def test_static_pages_render(cfg):
    c = client_for(cfg, Fake())
    for path in ("/", "/query", "/ontology"):
        r = c.get(path)
        assert r.status_code == 200 and "text/html" in r.content_type, path


# ---------- ontology ----------

def test_ontology_html_and_rdf(cfg):
    c = client_for(cfg, Fake())
    html = c.get("/ontology").get_data(as_text=True)
    assert "Player" in html and "playsFor" in html and "Team" in html
    ttl = c.get("/ontology", headers={"Accept": "text/turtle"})
    assert ttl.mimetype == "text/turtle" and ttl.headers["Content-Location"] == "/ontology.ttl"
    assert b"Player" in ttl.data
    assert json.loads(c.get("/ontology.jsonld").data)
    assert c.get("/ontology.pdf").status_code == 404


# ---------- playground API ----------

def api(c, query):
    return c.post("/api/query", json={"query": query})


def test_api_select_ask_and_graph(cfg):
    fake = Fake({"SELECT": result(["a", "b"], [{"a": {"type": "literal", "value": "1"}}])},
                construct="<a> <b> <c> .")
    fake.ask = lambda q: True
    c = client_for(cfg, fake)
    sel = api(c, "SELECT ?a ?b WHERE { ?a ?b ?c }").get_json()
    assert sel == {"form": "select", "vars": ["a", "b"], "rows": [{"a": "1", "b": None}], "truncated": False}
    assert api(c, "ASK { ?s ?p ?o }").get_json() == {"form": "ask", "boolean": True}
    assert api(c, "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }").get_json() == {
        "form": "graph", "turtle": "<a> <b> <c> .", "truncated": False}


def test_api_truncates_to_1000_rows(cfg):
    rows = [{"a": {"type": "literal", "value": str(i)}} for i in range(1001)]
    out = api(client_for(cfg, Fake({"SELECT": result(["a"], rows)})), "SELECT ?a WHERE { ?a ?b ?c }").get_json()
    assert len(out["rows"]) == 1000 and out["truncated"] is True


def test_api_rejects_updates_and_bad_input_without_calling_fuseki(cfg):
    fake = Fake()
    c = client_for(cfg, fake)
    r = api(c, "INSERT DATA { <a> <b> <c> }")
    assert r.status_code == 400 and "not allowed" in r.get_json()["error"]
    assert api(c, "").status_code == 400
    assert c.post("/api/query", json={"query": 5}).status_code == 400
    assert c.post("/api/query", data="not json").status_code == 400
    assert api(c, "SELECT * WHERE { ?s ?p ?o } # " + "x" * 20001).status_code == 400
    assert fake.queries == []
    assert api(c, 'SELECT * WHERE { ?s ?p "INSERT" }').status_code == 200


def test_api_maps_fuseki_errors(cfg):
    r = api(client_for(cfg, Fake(error=FusekiError("Parse error at line 1"))), "SELECT * WHERE { ?s ?p ?o }")
    assert r.status_code == 400 and r.get_json() == {"error": "Parse error at line 1"}
    r = api(client_for(cfg, Fake(error=FusekiUnavailable("connection refused"))), "SELECT * WHERE { ?s ?p ?o }")
    assert r.status_code == 502 and "SPARQL endpoint" in r.get_json()["error"]


def test_api_examples_lists_the_competency_queries(cfg):
    ex = client_for(cfg, Fake()).get("/api/examples").get_json()
    assert len(ex) == 9 and all(e["query"].strip() and e["name"] and e["id"] for e in ex)
    assert ex[0]["id"].startswith("q01")


# ---------- failure pages ----------

def test_fuseki_down_gives_clean_502_page(cfg):
    c = client_for(cfg, Fake(error=FusekiUnavailable("connection refused")))
    for path in ("/resource/player/10", "/page/player/10", "/search?q=saka"):
        r = c.get(path)
        text = r.get_data(as_text=True)
        assert r.status_code == 502 and "SPARQL endpoint" in text and "Traceback" not in text, path


def test_api_truncates_large_graph_results(cfg):
    big = "<a> <b> <c> .\n" * 200000                                   # about 2.8 MB of Turtle
    out = api(client_for(cfg, Fake(construct=big)), "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }").get_json()
    assert out["truncated"] is True and len(out["turtle"]) == 1000000


def test_server_errors_keep_fuseki_message_but_connection_errors_stay_generic(cfg):
    failing = client_for(cfg, Fake(error=FusekiFailure("Query timed out in Fuseki")))
    r = api(failing, "SELECT * WHERE { ?s ?p ?o }")
    assert r.status_code == 502 and "Query timed out in Fuseki" in r.get_json()["error"]
    page = failing.get("/search?q=saka").get_data(as_text=True)
    assert "Query timed out in Fuseki" in page
    down = api(client_for(cfg, Fake(error=FusekiUnavailable("[Errno 111] refused"))), "SELECT * WHERE { ?s ?p ?o }")
    assert "Is Fuseki running" in down.get_json()["error"] and "Errno" not in down.get_json()["error"]


def test_slow_or_oversized_queries_say_so(cfg):
    r = api(client_for(cfg, Fake(error=FusekiError("The query took longer than 60 seconds."))), "SELECT * WHERE { ?s ?p ?o }")
    assert r.status_code == 400 and "longer than 60 seconds" in r.get_json()["error"]


def test_playground_tells_the_user_to_type_their_own_query(cfg):
    html = client_for(cfg, Fake()).get("/query").get_data(as_text=True)
    assert "Type or paste your own SPARQL" in html           # the Example box only loads samples
    assert 'id="clear"' in html and 'id="q"' in html
