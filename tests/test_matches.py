from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from builders import matches
from helpers import FB, R, load_ttl


def test_club_match(ctx):
    n = matches.build(ctx)
    g = load_ttl(ctx.out_dir / "matches.ttl")
    m = URIRef(f"{R}match/100")
    assert (m, RDF.type, URIRef(FB + "Match")) in g
    assert (m, RDFS.label, Literal("Arsenal FC vs Tottenham Hotspur", lang="und")) in g
    assert (m, URIRef(FB + "homeTeam"), URIRef(f"{R}club/11")) in g
    assert (m, URIRef(FB + "awayTeam"), URIRef(f"{R}club/148")) in g
    assert (m, URIRef(FB + "homeScore"), Literal("2", datatype=XSD.integer)) in g
    assert (m, URIRef(FB + "matchDate"), Literal("2023-08-12", datatype=XSD.date)) in g
    assert (m, URIRef(FB + "inCompetition"), URIRef(f"{R}competition/GB1")) in g
    assert (m, URIRef(FB + "inSeason"), URIRef(f"{R}season/2023")) in g
    assert (m, URIRef(FB + "hostedAt"), URIRef(f"{R}stadium/Emirates_Stadium")) in g
    assert (m, URIRef(FB + "refereedBy"), URIRef(f"{R}referee/Michael_Oliver")) in g
    assert (m, URIRef(FB + "homeFormation"), Literal("4-3-3")) in g
    assert not list(g.objects(m, URIRef(FB + "awayFormation")))        # empty cell
    assert (URIRef(f"{R}season/2023"), URIRef(FB + "startYear"), Literal("2023", datatype=XSD.integer)) in g
    assert n == len(g)


def test_national_match_uses_national_team_uris_and_skips_empty_cells(ctx):
    matches.build(ctx)
    g = load_ttl(ctx.out_dir / "matches.ttl")
    m = URIRef(f"{R}match/200")
    assert (m, URIRef(FB + "homeTeam"), URIRef(f"{R}national-team/3299")) in g
    assert (m, URIRef(FB + "awayTeam"), URIRef(f"{R}national-team/9999")) in g
    assert not list(g.objects(m, URIRef(FB + "hostedAt")))             # stadium ""
    assert not list(g.objects(m, URIRef(FB + "refereedBy")))           # referee ""


def test_out_of_scope_match_skipped(ctx):
    matches.build(ctx)
    g = load_ttl(ctx.out_dir / "matches.ttl")
    assert not list(g.triples((URIRef(f"{R}match/101"), None, None)))
