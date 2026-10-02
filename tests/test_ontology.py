from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, OWL

FB = Namespace("https://example.org/football/ontology#")
ONT = Path(__file__).resolve().parents[1] / "ontology" / "football.ttl"

CLASSES = ["Team", "Club", "NationalTeam", "Player", "Match", "Competition", "Country", "Stadium",
           "Referee", "Manager", "Position", "Season", "MatchEvent", "Goal", "Card", "Substitution",
           "PenaltyShootoutKick", "Appearance", "Transfer", "MarketValuation"]


def graph():
    g = Graph()
    g.parse(str(ONT), format="turtle")
    return g


def test_classes_defined_with_label_and_comment():
    g = graph()
    for c in CLASSES:
        assert (FB[c], RDF.type, OWL.Class) in g, c
        assert (FB[c], RDFS.label, None) in g, c
        assert (FB[c], RDFS.comment, None) in g, c


def test_hierarchy():
    g = graph()
    assert (FB.Club, RDFS.subClassOf, FB.Team) in g
    assert (FB.NationalTeam, RDFS.subClassOf, FB.Team) in g
    assert (FB.Goal, RDFS.subClassOf, FB.MatchEvent) in g
    assert (FB.PenaltyShootoutKick, RDFS.subClassOf, FB.MatchEvent) in g


def test_every_property_has_label_comment_and_type():
    g = graph()
    props = set(g.subjects(RDF.type, OWL.ObjectProperty)) | set(g.subjects(RDF.type, OWL.DatatypeProperty))
    assert len(props) >= 60
    for p in props:
        assert (p, RDFS.label, None) in g, p
        assert (p, RDFS.comment, None) in g, p


def test_functional_and_inverse():
    g = graph()
    assert (FB.dateOfBirth, RDF.type, OWL.FunctionalProperty) in g
    assert (FB.hasPlayer, OWL.inverseOf, FB.playsFor) in g
