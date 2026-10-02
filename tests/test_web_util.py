import json
import urllib.error

import pytest
from rdflib import Graph, Literal, URIRef

from footballweb import fuseki, rdfio, sparqlutil


# ---------- escape_literal ----------

def test_escape_literal_neutralises_quotes_backslashes_and_newlines():
    assert sparqlutil.escape_literal('a"b') == 'a\\"b'
    assert sparqlutil.escape_literal("a\\b") == "a\\\\b"
    assert sparqlutil.escape_literal("a\nb\r\tc") == "a\\nb\\r\\tc"
    assert sparqlutil.escape_literal('"} UNION { ?s ?p ?o') == '\\"} UNION { ?s ?p ?o'


# ---------- query_form ----------

@pytest.mark.parametrize("query,form", [
    ("SELECT * WHERE { ?s ?p ?o }", "select"),
    ("PREFIX fb: <https://x/#>\nASK { ?s a fb:Player }", "ask"),
    ("# a comment\nCONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", "construct"),
    ("describe <https://x/y>", "describe"),
    ('SELECT * WHERE { ?s ?p "INSERT DELETE DROP" }', "select"),      # keywords inside a string
    ("SELECT * WHERE { ?s ?p ?add . ?s <https://x/load> ?o }", "select"),   # variable / IRI
    ("SELECT * WHERE { ?s fb:create ?o }  # DROP everything", "select"),   # prefixed name + comment
    ("SELECT * WHERE { ?s ?p 'it''s' } # don't DELETE", "select"),
    ("PREFIX ex: <http://x/> SELECT * { ?s ex:auto-delete ?o }", "select"),   # hyphen inside a local name
    ("PREFIX ex: <http://x/> SELECT * { ?s ex:v1.copy ?o }", "select"),       # dot inside a local name
    ('SELECT * WHERE { ?s ?p "x"@add }', "select"),                           # language tag
])
def test_query_form_accepts_read_queries(query, form):
    assert sparqlutil.query_form(query) == form


@pytest.mark.parametrize("query", [
    "INSERT DATA { <a> <b> <c> }",
    "DELETE WHERE { ?s ?p ?o }",
    "DROP ALL",
    "LOAD <http://x/y>",
    "CLEAR GRAPH <http://x/y>",
    "CREATE GRAPH <http://x/y>",
    "WITH <http://g> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }",
    "SELECT * WHERE { ?s ?p ?o } ; DROP ALL",
    "   ",
    "this is not sparql",
])
def test_query_form_rejects_updates_and_garbage(query):
    with pytest.raises(ValueError):
        sparqlutil.query_form(query)


# ---------- rdfio ----------

def graph():
    g = Graph()
    g.add((URIRef("https://x/a"), URIRef("http://www.w3.org/2000/01/rdf-schema#label"), Literal("Türkiye", lang="en")))
    return g


def test_serialize_every_format():
    g = graph()
    assert b"T\xc3\xbcrkiye" in rdfio.serialize(g, "ttl")
    assert json.loads(rdfio.serialize(g, "jsonld"))
    assert b"rdf:RDF" in rdfio.serialize(g, "rdf")
    assert rdfio.serialize(g, "nt").strip().endswith(b".")
    assert set(rdfio.EXTS) == {"ttl", "jsonld", "rdf", "nt"}
    assert rdfio.OFFERS[0] == "text/html" and rdfio.MIME_EXT["text/turtle"] == "ttl"


def test_parse_turtle_round_trip():
    g = rdfio.parse_turtle(rdfio.serialize(graph(), "ttl").decode())
    assert len(g) == 1


# ---------- FusekiClient ----------

class FakeResponse:
    def __init__(self, body):
        self.body = body.encode() if isinstance(body, str) else body
        self.pos = 0
    def read(self, n=-1):
        end = len(self.body) if n < 0 else self.pos + n
        chunk, self.pos = self.body[self.pos:end], min(end, len(self.body))
        return chunk
    def __enter__(self): return self
    def __exit__(self, *a): return False


def client_with(monkeypatch, behaviour):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append((req.full_url, req.data.decode(), req.get_header("Accept"), timeout))
        return behaviour(req)

    monkeypatch.setattr(fuseki.urllib.request, "urlopen", fake_urlopen)
    return fuseki.FusekiClient("http://h:3030/football/", timeout=7), calls


def test_client_select_ask_construct(monkeypatch):
    def behaviour(req):
        accept = req.get_header("Accept")
        if accept == "text/turtle":
            return FakeResponse("<a> <b> <c> .")
        return FakeResponse(json.dumps({"head": {"vars": []}, "boolean": True, "results": {"bindings": []}}))

    c, calls = client_with(monkeypatch, behaviour)
    assert c.select("SELECT 1")["results"]["bindings"] == []
    assert c.ask("ASK {}") is True
    assert c.construct("CONSTRUCT {} WHERE {}") == "<a> <b> <c> ."
    assert calls[0][0] == "http://h:3030/football/sparql"
    assert calls[0][1].startswith("query=") and calls[0][3] == 7
    assert calls[0][2] == "application/sparql-results+json" and calls[2][2] == "text/turtle"


def test_client_maps_http_and_network_errors(monkeypatch):
    def http(code, body):
        def behaviour(req):
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, __import__("io").BytesIO(body.encode()))
        return behaviour

    c, _ = client_with(monkeypatch, http(400, "Parse error: unexpected }"))
    with pytest.raises(fuseki.FusekiError, match="Parse error"):
        c.select("bad")
    c, _ = client_with(monkeypatch, http(503, "overloaded"))
    with pytest.raises(fuseki.FusekiUnavailable):
        c.select("x")

    def down(req):
        raise urllib.error.URLError("connection refused")

    c, _ = client_with(monkeypatch, down)
    with pytest.raises(fuseki.FusekiUnavailable):
        c.ask("ASK {}")


# ---------- FusekiClient limits and error detail ----------

def test_client_sends_a_fuseki_side_timeout(monkeypatch):
    c, calls = client_with(monkeypatch, lambda req: FakeResponse("{}"))
    c.select("SELECT 1")
    assert "timeout=7000" in calls[0][1]


def test_client_aborts_results_larger_than_the_byte_cap(monkeypatch):
    c, _ = client_with(monkeypatch, lambda req: FakeResponse(b"x" * 5000))
    c.max_bytes = 1000
    with pytest.raises(fuseki.FusekiError, match="larger than"):
        c.select("SELECT * { ?s ?p ?o }")


def test_client_enforces_a_total_deadline(monkeypatch):
    ticks = iter(range(0, 1000, 5))                        # every clock reading is 5 s later
    monkeypatch.setattr(fuseki.time, "monotonic", lambda: next(ticks))
    c, _ = client_with(monkeypatch, lambda req: FakeResponse(b"x" * 200000))
    with pytest.raises(fuseki.FusekiError, match="longer than 7 seconds"):
        c.select("SELECT * { ?s ?p ?o }")


def test_client_reports_a_socket_timeout_as_a_slow_query(monkeypatch):
    def slow(req):
        raise TimeoutError("timed out")
    c, _ = client_with(monkeypatch, slow)
    with pytest.raises(fuseki.FusekiError, match="longer than 7 seconds"):
        c.select("SELECT 1")


def test_client_keeps_the_body_of_a_server_error(monkeypatch):
    def boom(req):
        raise urllib.error.HTTPError(req.full_url, 500, "x", {}, __import__("io").BytesIO(b"Query timed out in Fuseki"))
    c, _ = client_with(monkeypatch, boom)
    with pytest.raises(fuseki.FusekiFailure, match="timed out in Fuseki"):
        c.select("x")
    assert issubclass(fuseki.FusekiFailure, fuseki.FusekiUnavailable)
