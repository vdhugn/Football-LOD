from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from builders import reference
from helpers import FB, R, load_ttl


def build(ctx):
    n = reference.build(ctx)
    return n, load_ttl(ctx.out_dir / "reference.ttl")


def test_countries_and_national_teams(ctx):
    n, g = build(ctx)
    england = URIRef(f"{R}country/189")
    assert (england, RDF.type, URIRef(FB + "Country")) in g
    assert (england, RDFS.label, Literal("England", lang="en")) in g
    nt = URIRef(f"{R}national-team/3299")
    assert (nt, RDF.type, URIRef(FB + "NationalTeam")) in g
    assert (nt, URIRef(FB + "country"), england) in g
    assert (nt, URIRef(FB + "fifaRanking"), Literal("4", datatype=XSD.integer)) in g
    assert (nt, URIRef(FB + "averageAge"), Literal("27.1", datatype=XSD.decimal)) in g
    assert (nt, URIRef(FB + "managedBy"), URIRef(f"{R}manager/Gareth_Southgate")) in g
    assert n == len(g)


def test_competitions_international_has_no_country(ctx):
    _, g = build(ctx)
    gb1, wc = URIRef(f"{R}competition/GB1"), URIRef(f"{R}competition/FIWC")
    assert (gb1, URIRef(FB + "country"), URIRef(f"{R}country/189")) in g
    assert (gb1, URIRef(FB + "competitionType"), Literal("domestic_league")) in g
    assert (wc, RDF.type, URIRef(FB + "Competition")) in g
    assert not list(g.objects(wc, URIRef(FB + "country")))   # country_id = -1


def test_optional_cells_do_not_create_triples(ctx):
    _, g = build(ctx)
    turkiye = URIRef(f"{R}country/50")
    assert not list(g.objects(turkiye, URIRef("http://www.w3.org/2000/01/rdf-schema#seeAlso")))
