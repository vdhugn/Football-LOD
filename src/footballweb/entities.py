"""Entity model: SPARQL queries and view data for search results and entity pages."""
import re
from decimal import Decimal, InvalidOperation

from common import Uris, clean

from .sparqlutil import escape_literal

KIND_RE = re.compile(r"^[a-z][a-z-]*$")
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
FOAF_DEPICTION = "http://xmlns.com/foaf/0.1/depiction"
EXTERNAL = {
    "http://www.w3.org/2002/07/owl#sameAs",
    "http://www.w3.org/2004/02/skos/core#closeMatch",
    "http://www.w3.org/2000/01/rdf-schema#seeAlso",
    FOAF_DEPICTION,
}
NUMERIC = ("integer", "decimal", "double", "float")
PLAIN_NUMBERS = {"lastSeason", "startYear"}      # years, shown without thousands separators


def short(uri):
    return re.split(r"[#/]", uri.rstrip("/"))[-1]


def fmt_number(text):
    try:
        d = Decimal(text)
    except InvalidOperation:
        return text
    return f"{d:,.0f}" if d == d.to_integral_value() else f"{d:,}"


def _val(binding, name):
    cell = binding.get(name)
    return cell["value"] if cell else None


class Entities:
    def __init__(self, client, cfg):
        self.client = client
        self.uris = Uris(cfg)
        self.base = cfg["resource_base"]
        self.prefixes = (f"PREFIX fb: <{cfg['ontology_base']}>\n"
                         "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n")

    # ---------- URIs ----------

    def iri(self, kind, key):
        return self.uris.res(kind, key)

    def local(self, uri):
        """Canonical resource URI -> local page path, or None for foreign URIs."""
        return "/page/" + uri[len(self.base):] if uri.startswith(self.base) else None

    # ---------- raw access ----------

    def exists(self, iri):
        return self.client.ask(f"ASK {{ {iri} ?p ?o }}")

    def describe_graph(self, iri):
        return self.client.construct(f"CONSTRUCT {{ {iri} ?p ?o }} WHERE {{ {iri} ?p ?o }}")

    # ---------- search ----------

    def search(self, text):
        needle = escape_literal(text.lower())
        q = (self.prefixes +
             "SELECT ?s ?label ?type WHERE { "
             "VALUES ?type { fb:Player fb:Club fb:NationalTeam fb:Competition fb:Country } "
             "?s a ?type ; rdfs:label ?label . "
             f'FILTER(CONTAINS(LCASE(STR(?label)), "{needle}")) '
             "} ORDER BY ?label LIMIT 25")
        out = []
        for b in self.client.select(q)["results"]["bindings"]:
            href = self.local(b["s"]["value"])
            if href:
                out.append({"label": b["label"]["value"], "type": short(b["type"]["value"]), "href": href})
        return out

    # ---------- entity page ----------

    def _item(self, o, olabel, pred=None):
        if o["type"] == "uri":
            href = self.local(o["value"])
            return {"kind": "uri", "text": olabel or short(o["value"]), "href": href or o["value"],
                    "internal": href is not None, "meta": None}
        dt = short(o["datatype"]) if o.get("datatype") else None
        text = fmt_number(o["value"]) if dt in NUMERIC and short(pred or "") not in PLAIN_NUMBERS else o["value"]
        return {"kind": "literal", "text": text, "href": None, "internal": False,
                "meta": dt or o.get("xml:lang")}

    def page(self, kind, key):
        iri = self.iri(kind, key)
        if iri is None:
            return None
        q = (self.prefixes +
             f"SELECT ?p ?o (SAMPLE(?l) AS ?ol) WHERE {{ {iri} ?p ?o . OPTIONAL {{ ?o rdfs:label ?l }} }} "
             "GROUP BY ?p ?o ORDER BY ?p LIMIT 500")
        rows = self.client.select(q)["results"]["bindings"]
        if not rows:
            return None
        uri = iri[1:-1]
        title, types, external, depiction, groups = None, [], [], None, {}
        for b in rows:
            p, o = b["p"]["value"], b["o"]
            if p == RDF_TYPE:
                types.append(short(o["value"]))
            elif p in EXTERNAL:
                external.append({"pred": short(p), "uri": o["value"]})
                if p == FOAF_DEPICTION:
                    depiction = o["value"]
            else:
                if p == RDFS_LABEL and title is None:
                    title = o["value"]
                groups.setdefault(p, []).append(self._item(o, _val(b, "ol"), p))
        return {
            "title": title or uri, "uri": uri, "types": types, "depiction": depiction,
            "external": external,
            "groups": [{"name": short(p), "entries": v} for p, v in sorted(groups.items(), key=lambda kv: short(kv[0]))],
            "related": self._related(kind, iri),
        }

    # ---------- kind-specific sections ----------

    def _related(self, kind, iri):
        if kind == "player":
            return {"transfers": self._transfers(iri), "valuations": self._valuations(iri),
                    "totals": self._totals(iri)}
        if kind == "club":
            return {"squad": self._squad(iri)}
        return {}

    def _club_ref(self, b, uri_name, label_name):
        uri = _val(b, uri_name)
        return {"text": _val(b, label_name) or short(uri), "href": self.local(uri) or uri}

    def _transfers(self, iri):
        q = (self.prefixes +
             f"SELECT ?date ?from ?fl ?to ?tl ?fee WHERE {{ ?t fb:transferOf {iri} ; fb:transferDate ?date ; "
             "fb:fromClub ?from ; fb:toClub ?to . OPTIONAL { ?t fb:transferFee ?fee } "
             "OPTIONAL { ?from rdfs:label ?fl } OPTIONAL { ?to rdfs:label ?tl } } "
             "ORDER BY DESC(?date) LIMIT 50")
        out = []
        for b in self.client.select(q)["results"]["bindings"]:
            fee = _val(b, "fee")
            out.append({"date": _val(b, "date"), "from": self._club_ref(b, "from", "fl"),
                        "to": self._club_ref(b, "to", "tl"), "fee": fmt_number(fee) if fee else None})
        return out

    def _valuations(self, iri):
        q = (self.prefixes +
             f"SELECT ?date ?value WHERE {{ ?v fb:valuationOf {iri} ; fb:valuationDate ?date ; fb:valueEUR ?value }} "
             "ORDER BY DESC(?date) LIMIT 100")
        return [{"date": _val(b, "date"), "value": fmt_number(_val(b, "value"))}
                for b in self.client.select(q)["results"]["bindings"]]

    def _totals(self, iri):
        q = (self.prefixes +
             f"SELECT (COUNT(?a) AS ?apps) (SUM(?g) AS ?goals) WHERE {{ ?a fb:appearanceOf {iri} . "
             "OPTIONAL { ?a fb:goals ?g } }")
        rows = self.client.select(q)["results"]["bindings"]
        b = rows[0] if rows else {}
        return {"appearances": _val(b, "apps") or "0", "goals": _val(b, "goals") or "0"}

    def _squad(self, iri):
        q = (self.prefixes +
             f"SELECT ?p ?label ?value WHERE {{ ?p fb:playsFor {iri} ; rdfs:label ?label . "
             "OPTIONAL { ?p fb:currentMarketValueEUR ?value } } ORDER BY DESC(?value) LIMIT 60")
        out = []
        for b in self.client.select(q)["results"]["bindings"]:
            href = self.local(_val(b, "p"))
            if href:
                value = _val(b, "value")
                out.append({"text": _val(b, "label"), "href": href, "value": fmt_number(value) if value else None})
        return out
