from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from builders import facts
from helpers import FB, R, load_ttl


def test_split_description():
    assert facts.split_description("1. Yellow card  , Foul") == ("1. Yellow card", "Foul")
    assert facts.split_description(", Tactical") == (None, "Tactical")
    assert facts.split_description("") == (None, None)
    assert facts.split_description(None) == (None, None)


def test_appearances(ctx):
    n = facts.build_appearances(ctx)
    g = load_ttl(ctx.out_dir / "appearances.ttl")
    a = URIRef(f"{R}appearance/100_10")
    assert (a, RDF.type, URIRef(FB + "Appearance")) in g
    assert (a, URIRef(FB + "appearanceOf"), URIRef(f"{R}player/10")) in g
    assert (a, URIRef(FB + "inMatch"), URIRef(f"{R}match/100")) in g
    assert (a, URIRef(FB + "forTeam"), URIRef(f"{R}club/11")) in g
    assert (a, URIRef(FB + "goals"), Literal("1", datatype=XSD.integer)) in g
    assert (a, URIRef(FB + "minutesPlayed"), Literal("90", datatype=XSD.integer)) in g
    # World Cup appearance is attributed to the national team
    wc = URIRef(f"{R}appearance/200_10")
    assert (wc, URIRef(FB + "forTeam"), URIRef(f"{R}national-team/3299")) in g
    # appearance in an out-of-scope game is skipped
    assert not list(g.triples((URIRef(f"{R}appearance/101_30"), None, None)))
    assert n == len(g)


def test_events(ctx):
    n = facts.build_events(ctx)
    g = load_ttl(ctx.out_dir / "events.ttl")
    goal = URIRef(f"{R}event/e1")
    assert (goal, RDF.type, URIRef(FB + "Goal")) in g
    assert (goal, URIRef(FB + "byPlayer"), URIRef(f"{R}player/10")) in g
    assert (goal, URIRef(FB + "assistedBy"), URIRef(f"{R}player/20")) in g
    assert (goal, URIRef(FB + "minute"), Literal("10", datatype=XSD.integer)) in g
    assert (goal, URIRef(FB + "forTeam"), URIRef(f"{R}club/11")) in g
    card = URIRef(f"{R}event/e2")
    assert (card, RDF.type, URIRef(FB + "Card")) in g
    assert (card, URIRef(FB + "cardType"), Literal("Yellow card")) in g
    assert (card, RDFS.comment, Literal("Foul")) in g
    sub = URIRef(f"{R}event/e3")
    assert (sub, RDF.type, URIRef(FB + "Substitution")) in g
    assert (sub, URIRef(FB + "playerOut"), URIRef(f"{R}player/10")) in g
    assert (sub, URIRef(FB + "playerIn"), URIRef(f"{R}player/20")) in g
    kick = URIRef(f"{R}event/e4")
    assert (kick, RDF.type, URIRef(FB + "PenaltyShootoutKick")) in g
    assert (kick, URIRef(FB + "scored"), Literal(True)) in g
    assert (kick, URIRef(FB + "forTeam"), URIRef(f"{R}national-team/3299")) in g
    assert n == len(g)


def test_unknown_event_type_is_counted_not_fatal(ctx, data_dir):
    from helpers import put
    put(data_dir, "game_events.csv", [
        {"game_event_id": "x1", "game_id": "100", "minute": "1", "type": "VAR", "club_id": "11", "player_id": "10"},
    ])
    facts.build_events(ctx)
    assert ctx.notes["event_unknown_type"] == 1
