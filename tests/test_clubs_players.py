from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, SKOS, XSD

from builders import clubs, players
from countries import CountryResolver
from helpers import FB, R, load_ttl


def test_full_and_minimal_clubs(ctx):
    n = clubs.build(ctx)
    g = load_ttl(ctx.out_dir / "clubs.ttl")
    arsenal = URIRef(f"{R}club/11")
    assert (arsenal, RDFS.label, Literal("Arsenal FC", lang="und")) in g
    assert (arsenal, URIRef(FB + "netTransferRecordEUR"), Literal("5900000", datatype=XSD.decimal)) in g
    assert (arsenal, URIRef(FB + "domesticCompetition"), URIRef(f"{R}competition/GB1")) in g
    assert (arsenal, URIRef(FB + "homeStadium"), URIRef(f"{R}stadium/Emirates_Stadium")) in g
    assert (URIRef(f"{R}stadium/Emirates_Stadium"), URIRef(FB + "stadiumSeats"),
            Literal("60704", datatype=XSD.integer)) in g
    # clubs 148 and 999 are not in clubs.csv -> minimal nodes with names from other tables
    assert (URIRef(f"{R}club/148"), RDFS.label, Literal("Tottenham Hotspur", lang="und")) in g
    assert (URIRef(f"{R}club/999"), RDFS.label, Literal("Hale End", lang="und")) in g
    assert (URIRef(f"{R}club/999"), RDF.type, URIRef(FB + "Club")) in g
    assert ctx.notes["club_minimal"] == 2
    assert n == len(g)


def test_league_missing_from_competitions_csv_gets_minimal_node(ctx):
    clubs.build(ctx)
    g = load_ttl(ctx.out_dir / "clubs.ttl")
    col1 = URIRef(f"{R}competition/COL1")
    assert (URIRef(f"{R}club/888"), URIRef(FB + "domesticCompetition"), col1) in g
    assert (col1, RDF.type, URIRef(FB + "Competition")) in g
    assert not list(g.triples((URIRef(f"{R}competition/GB1"), None, None)))   # known: described in reference.ttl
    assert ctx.notes["competition_minimal"] == 1


def test_player_values_and_nulls(ctx):
    players.build(ctx)
    g = load_ttl(ctx.out_dir / "players.ttl")
    p = URIRef(f"{R}player/10")
    assert (p, URIRef(FB + "dateOfBirth"), Literal("2001-09-05", datatype=XSD.date)) in g
    assert (p, URIRef(FB + "birthCity"), Literal("London")) in g           # trimmed
    assert (p, URIRef(FB + "heightCm"), Literal("178", datatype=XSD.integer)) in g
    assert (p, URIRef(FB + "playsFor"), URIRef(f"{R}club/11")) in g
    assert (p, URIRef(FB + "representsNationalTeam"), URIRef(f"{R}national-team/3299")) in g
    assert (p, URIRef(FB + "citizenOf"), URIRef(f"{R}country/189")) in g
    assert (p, URIRef(FB + "position"), URIRef(f"{R}position/Attack")) in g
    assert (p, URIRef(FB + "subPosition"), URIRef(f"{R}position/Right_Winger")) in g
    assert (URIRef(f"{R}position/Right_Winger"), SKOS.broader, URIRef(f"{R}position/Attack")) in g
    son = URIRef(f"{R}player/20")                                          # almost all cells empty
    assert not list(g.objects(son, URIRef(FB + "dateOfBirth")))
    assert not list(g.objects(son, URIRef(FB + "position")))               # position "Missing"
    assert not list(g.objects(son, URIRef(FB + "heightCm")))


def test_out_of_scope_player_excluded_and_unknown_country_minimal(ctx):
    players.build(ctx)
    g = load_ttl(ctx.out_dir / "players.ttl")
    assert not list(g.triples((URIRef(f"{R}player/30"), None, None)))
    extra = URIRef(f"{R}country/n-Korea%2C_South")      # Uris.res percent-encodes the comma
    assert (URIRef(f"{R}player/20"), URIRef(FB + "citizenOf"), extra) in g
    assert (extra, RDF.type, URIRef(FB + "Country")) in g


def test_player_missing_from_players_csv_gets_minimal_node(ctx):
    ctx.scope.player_ids.add("777")
    players.build(ctx)
    g = load_ttl(ctx.out_dir / "players.ttl")
    assert (URIRef(f"{R}player/777"), RDF.type, URIRef(FB + "Player")) in g
    assert ctx.notes["player_minimal"] == 1


def test_country_resolver_alias_and_names(ctx):
    r = CountryResolver(ctx)
    assert r.uri("Turkey") == f"<{R}country/50>"      # alias to Türkiye
    assert r.uri("England") == f"<{R}country/189>"
    assert r.uri("") is None and r.uri(None) is None
    assert "England" in r.all_names()
