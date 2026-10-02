"""RDF serialisation formats offered by the web app."""
from rdflib import Graph

EXTS = {
    "ttl": ("text/turtle", "turtle"),
    "jsonld": ("application/ld+json", "json-ld"),
    "rdf": ("application/rdf+xml", "xml"),
    "nt": ("application/n-triples", "nt"),
}
MIME_EXT = {mime: ext for ext, (mime, _) in EXTS.items()}
OFFERS = ["text/html"] + list(MIME_EXT)


def parse_turtle(text):
    g = Graph()
    g.parse(data=text, format="turtle")
    return g


def serialize(graph, ext):
    return graph.serialize(format=EXTS[ext][1]).encode("utf-8")
