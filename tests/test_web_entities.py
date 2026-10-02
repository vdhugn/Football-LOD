import pytest

from footballweb import entities
from footballweb.entities import Entities, fmt_number, short
from helpers import FB, R

LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
SAME = "http://www.w3.org/2002/07/owl#sameAs"
DEPICT = "http://xmlns.com/foaf/0.1/depiction"


def uri(v, label=None):
    row = {"type": "uri", "value": v}
    return row


def lit(v, datatype=None, lang=None):
    d = {"type": "literal", "value": v}
    if datatype:
        d["datatype"] = datatype
    if lang:
        d["xml:lang"] = lang
    return d


def row(p, o, ol=None):
    b = {"p": {"type": "uri", "value": p}, "o": o}
    if ol:
        b["ol"] = lit(ol)
    return b


def result(vars_, rows):
    return {"head": {"vars": vars_}, "results": {"bindings": rows}}


class Fake:
    """Answers SPARQL by looking for a marker in the query text."""
    def __init__(self, routes, ask=True, construct=""):
        self.routes, self._ask, self._construct, self.queries = routes, ask, construct, []

    def select(self, q):
        self.queries.append(q)
        for marker, data in self.routes.items():
            if marker in q:
                return data
        return result([], [])

    def ask(self, q):
        self.queries.append(q)
        return self._ask

    def construct(self, q):
        self.queries.append(q)
        return self._construct


@pytest.fixture
def cfg():
    return {"ontology_base": FB, "resource_base": R}


def test_short_and_fmt_number():
    assert short("https://x/y#Player") == "Player" and short("https://x/y/z/") == "z"
    assert fmt_number("120000000") == "120,000,000"
    assert fmt_number("120000000.0") == "120,000,000"
    assert fmt_number("27.1") == "27.1"
    assert fmt_number("abc") == "abc"


def test_iri_validates_and_quotes(cfg):
    e = Entities(Fake({}), cfg)
    assert e.iri("player", "10") == f"<{R}player/10>"
    assert e.iri("stadium", "Allianz Arena") == f"<{R}stadium/Allianz%20Arena>"
    assert e.iri("player", "") is None


def test_search_escapes_user_text_and_lowercases(cfg):
    fake = Fake({"?label": result(["s", "label", "type"], [
        {"s": uri(f"{R}player/10"), "label": lit("Bukayo Saka"), "type": uri(FB + "Player")}])})
    e = Entities(fake, cfg)
    out = e.search('O"Brien\\ \n')
    q = fake.queries[0]
    assert 'o\\"brien\\\\ \\n' in q                       # lower-cased and escaped, still one literal
    assert "LIMIT 25" in q
    assert out == [{"label": "Bukayo Saka", "type": "Player", "href": "/page/player/10"}]


def test_search_skips_foreign_uris(cfg):
    fake = Fake({"?label": result(["s", "label", "type"], [
        {"s": uri("https://other.example/x"), "label": lit("X"), "type": uri(FB + "Club")}])})
    assert Entities(fake, cfg).search("x") == []


def player_rows():
    return [
        row(TYPE, uri(FB + "Player")),
        row(LABEL, lit("Bukayo Saka", lang="und")),
        row(FB + "playsFor", uri(f"{R}club/11"), "Arsenal FC"),
        row(FB + "heightCm", lit("178", datatype="http://www.w3.org/2001/XMLSchema#integer")),
        row(FB + "currentMarketValueEUR", lit("120000000.0", datatype="http://www.w3.org/2001/XMLSchema#decimal")),
        row(SAME, uri("http://www.wikidata.org/entity/Q1")),
        row(DEPICT, uri("https://img.example/10.jpg")),
    ]


def test_page_player(cfg):
    fake = Fake({
        "GROUP BY ?p ?o": result(["p", "o", "ol"], player_rows()),
        "fb:transferOf": result(["date", "from", "fl", "to", "tl", "fee"], [{
            "date": lit("2023-01-01"), "from": uri(f"{R}club/11"), "fl": lit("Arsenal FC"),
            "to": uri(f"{R}club/148"), "tl": lit("Tottenham Hotspur"), "fee": lit("5000000.0")}]),
        "fb:valuationOf": result(["date", "value"], [{"date": lit("2023-06-01"), "value": lit("100000000.0")}]),
        "COUNT(?a)": result(["apps", "goals"], [{"apps": lit("12"), "goals": lit("3")}]),
    })
    p = Entities(fake, cfg).page("player", "10")
    assert p["title"] == "Bukayo Saka" and p["types"] == ["Player"]
    assert p["uri"] == f"{R}player/10"
    assert p["depiction"] == "https://img.example/10.jpg"
    assert p["external"] == [{"pred": "sameAs", "uri": "http://www.wikidata.org/entity/Q1"},
                             {"pred": "depiction", "uri": "https://img.example/10.jpg"}]   # spec 3.2: also listed
    names = [g["name"] for g in p["groups"]]
    assert names == sorted(names) and "playsFor" in names and "sameAs" not in names and "type" not in names
    plays = next(g for g in p["groups"] if g["name"] == "playsFor")["entries"][0]
    assert plays == {"kind": "uri", "text": "Arsenal FC", "href": "/page/club/11", "internal": True, "meta": None}
    value = next(g for g in p["groups"] if g["name"] == "currentMarketValueEUR")["entries"][0]
    assert value["text"] == "120,000,000" and value["meta"] == "decimal"
    rel = p["related"]
    assert rel["transfers"] == [{"date": "2023-01-01", "from": {"text": "Arsenal FC", "href": "/page/club/11"},
                                 "to": {"text": "Tottenham Hotspur", "href": "/page/club/148"}, "fee": "5,000,000"}]
    assert rel["valuations"] == [{"date": "2023-06-01", "value": "100,000,000"}]
    assert rel["totals"] == {"appearances": "12", "goals": "3"}


def test_page_club_squad(cfg):
    fake = Fake({
        "GROUP BY ?p ?o": result(["p", "o", "ol"], [row(TYPE, uri(FB + "Club")), row(LABEL, lit("Arsenal FC"))]),
        "fb:playsFor": result(["p", "label", "value"], [
            {"p": uri(f"{R}player/10"), "label": lit("Bukayo Saka"), "value": lit("120000000.0")},
            {"p": uri(f"{R}player/20"), "label": lit("Unvalued")}]),
    })
    p = Entities(fake, cfg).page("club", "11")
    assert p["related"] == {"squad": [
        {"text": "Bukayo Saka", "href": "/page/player/10", "value": "120,000,000"},
        {"text": "Unvalued", "href": "/page/player/20", "value": None}]}


def test_page_other_kinds_have_no_related_and_unknown_is_none(cfg):
    fake = Fake({"GROUP BY ?p ?o": result(["p", "o", "ol"], [row(LABEL, lit("Premier League"))])})
    assert Entities(fake, cfg).page("competition", "GB1")["related"] == {}
    assert Entities(Fake({}), cfg).page("player", "999") is None          # no triples
    assert Entities(Fake({}), cfg).page("player", "") is None


def test_title_falls_back_to_uri(cfg):
    fake = Fake({"GROUP BY ?p ?o": result(["p", "o", "ol"], [row(FB + "goals", lit("1"))])})
    assert Entities(fake, cfg).page("appearance", "a1")["title"] == f"{R}appearance/a1"


def test_year_values_are_not_given_thousands_separators(cfg):
    xsd = "http://www.w3.org/2001/XMLSchema#integer"
    rows = [row(FB + "lastSeason", lit("2025", datatype=xsd)), row(FB + "startYear", lit("2023", datatype=xsd)),
            row(FB + "stadiumSeats", lit("60704", datatype=xsd))]
    fake = Fake({"GROUP BY ?p ?o": result(["p", "o", "ol"], rows)})
    groups = {g["name"]: g["entries"][0]["text"] for g in Entities(fake, cfg).page("club", "11")["groups"]}
    assert groups == {"lastSeason": "2025", "startYear": "2023", "stadiumSeats": "60,704"}
