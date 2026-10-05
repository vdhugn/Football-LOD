"""Flask application: entity pages, content negotiation, ontology and SPARQL playground."""
import os
from pathlib import Path

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for
from rdflib import OWL, RDF, RDFS, Graph

from common import load_config

from .ask import Asker, AskError
from .entities import KIND_RE, Entities, short
from .fuseki import FusekiClient, FusekiError, FusekiFailure, FusekiUnavailable
from .rdfio import EXTS, MIME_EXT, OFFERS, parse_turtle, serialize
from .sparqlutil import query_form

ROOT = Path(__file__).resolve().parents[2]
MAX_ROWS = 1000
MAX_QUERY_CHARS = 20000
MAX_GRAPH_CHARS = 1000000
UNAVAILABLE = "The SPARQL endpoint could not be reached. Is Fuseki running (scripts/load.sh)?"


def summarize_ontology(g, onto_base):
    def local(term):
        s = str(term)
        return s[len(onto_base):] if s.startswith(onto_base) else short(s)

    def comment(term):
        c = g.value(term, RDFS.comment)
        return str(c) if c else ""

    classes = []
    for c in sorted(g.subjects(RDF.type, OWL.Class), key=str):
        if str(c).startswith(onto_base):
            classes.append({"name": local(c), "comment": comment(c),
                            "parents": [local(p) for p in g.objects(c, RDFS.subClassOf) if str(p).startswith(onto_base)]})
    props = []
    for kind, typ in (("object", OWL.ObjectProperty), ("datatype", OWL.DatatypeProperty)):
        for p in sorted(g.subjects(RDF.type, typ), key=str):
            if str(p).startswith(onto_base):
                dom, rng = g.value(p, RDFS.domain), g.value(p, RDFS.range)
                props.append({"name": local(p), "kind": kind, "comment": comment(p),
                              "domain": local(dom) if dom else "", "range": local(rng) if rng else ""})
    return {"classes": classes, "properties": sorted(props, key=lambda x: x["name"])}


def create_app(cfg=None, client=None, root=ROOT):
    root = Path(root)
    cfg = cfg or load_config(root / "config.json")
    client = client or FusekiClient(os.environ.get("FUSEKI_URL", "http://localhost:3030/football"))
    app = Flask(__name__)
    ent = Entities(client, cfg)
    asker = Asker(client, cfg)

    ontology = Graph()
    ontology.parse(str(root / "ontology" / "football.ttl"), format="turtle")
    onto_summary = summarize_ontology(ontology, cfg["ontology_base"])

    def examples():
        out = []
        for f in sorted((root / "queries").glob("q*.rq")):
            text = f.read_text(encoding="utf-8")
            title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), f.stem)
            out.append({"id": f.stem, "name": title, "query": text})
        return out

    def check_kind(kind):
        if not KIND_RE.match(kind):
            abort(404)

    def best_offer():
        return request.accept_mimetypes.best_match(OFFERS, default="text/html")

    # ---------- error handling ----------

    @app.errorhandler(FusekiUnavailable)
    def unavailable(e):
        message = f"The SPARQL endpoint reported an error: {e}" if isinstance(e, FusekiFailure) else UNAVAILABLE
        if request.path.startswith("/api/"):
            return jsonify(error=message), 502
        return render_template("error.html", title="Endpoint unavailable", message=message), 502

    @app.errorhandler(FusekiError)
    def rejected(e):
        if request.path.startswith("/api/"):
            return jsonify(error=str(e)), 400
        return render_template("error.html", title="Query rejected", message=str(e)), 400

    @app.errorhandler(AskError)
    def not_understood(e):
        return jsonify(error=str(e), suggestions=e.suggestions), 400

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", title="Not found", message="Nothing here."), 404

    # ---------- pages ----------

    @app.get("/")
    def index():
        return render_template("index.html", examples=examples())

    @app.get("/search")
    def search():
        q = (request.args.get("q") or "").strip()
        error, results = None, []
        if q:
            if not 2 <= len(q) <= 80:
                error = "Type between 2 and 80 characters."
            else:
                results = ent.search(q)
        return render_template("search.html", q=q, results=results, error=error), (400 if error else 200)

    @app.get("/resource/<kind>/<path:key>")
    def resource(kind, key):
        check_kind(kind)
        iri = ent.iri(kind, key)
        if iri is None or not ent.exists(iri):
            abort(404)
        best = best_offer()
        if best == "text/html":
            return redirect(url_for("page", kind=kind, key=key), 303)
        return redirect(url_for("data", kind=kind, name=f"{key}.{MIME_EXT[best]}"), 303)

    @app.get("/page/<kind>/<path:key>")
    def page(kind, key):
        check_kind(kind)
        entity = ent.page(kind, key)
        if entity is None:
            abort(404)
        return render_template("entity.html", e=entity, kind=kind, key=key, exts=list(EXTS))

    @app.get("/data/<kind>/<path:name>")
    def data(kind, name):
        check_kind(kind)
        key, dot, ext = name.rpartition(".")
        if not dot or ext not in EXTS:
            abort(404)
        iri = ent.iri(kind, key)
        if iri is None:
            abort(404)
        graph = parse_turtle(ent.describe_graph(iri))
        if len(graph) == 0:
            abort(404)
        return Response(serialize(graph, ext), mimetype=EXTS[ext][0])

    @app.get("/ontology")
    @app.get("/ontology.<ext>")
    def ontology_view(ext=None):
        if ext is None:
            best = best_offer()
            if best == "text/html":
                return render_template("ontology.html", o=onto_summary, base=cfg["ontology_base"], exts=list(EXTS))
            ext = MIME_EXT[best]
        elif ext not in EXTS:
            abort(404)
        resp = Response(serialize(ontology, ext), mimetype=EXTS[ext][0])
        resp.headers["Content-Location"] = f"/ontology.{ext}"
        return resp

    # ---------- playground ----------

    @app.get("/query")
    def query_page():
        return render_template("query.html", resource_base=cfg["resource_base"])

    @app.get("/api/examples")
    def api_examples():
        return jsonify(examples())

    @app.post("/api/ask")
    def api_ask():
        payload = request.get_json(silent=True)
        text = payload.get("question") if isinstance(payload, dict) else None
        if not isinstance(text, str):
            return jsonify(error="Send a question as JSON: {\"question\": \"...\"}.", suggestions=[]), 400
        return jsonify(asker.answer(text))

    @app.post("/api/query")
    def api_query():
        payload = request.get_json(silent=True)
        text = payload.get("query") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            return jsonify(error="Enter a SPARQL query."), 400
        if len(text) > MAX_QUERY_CHARS:
            return jsonify(error=f"The query is longer than {MAX_QUERY_CHARS} characters."), 400
        try:
            form = query_form(text)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        if form == "select":
            res = client.select(text)
            names = res["head"]["vars"]
            bindings = res["results"]["bindings"]
            rows = [{n: (b[n]["value"] if n in b else None) for n in names} for b in bindings[:MAX_ROWS]]
            return jsonify(form="select", vars=names, rows=rows, truncated=len(bindings) > MAX_ROWS)
        if form == "ask":
            return jsonify(form="ask", boolean=client.ask(text))
        turtle = client.construct(text)
        return jsonify(form="graph", turtle=turtle[:MAX_GRAPH_CHARS], truncated=len(turtle) > MAX_GRAPH_CHARS)

    return app
