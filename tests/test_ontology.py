from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS, OWL

FB = Namespace("https://vdhugn.github.io/Football-LOD/ontology#")
ONT = Path(__file__).resolve().parents[1] / "ontology" / "football.ttl"

CLASSES = ["Team", "Club", "NationalTeam", "Player", "Competition", "Country", "Stadium",
           "Manager", "Position", "Transfer", "MarketValuation"]
REMOVED = ["Match", "Season", "Referee", "MatchEvent", "Goal", "Card", "Substitution",
           "PenaltyShootoutKick", "Appearance", "appearanceOf", "inMatch", "homeTeam", "goals", "minute"]


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


def test_match_vocabulary_is_gone():
    g = graph()
    for t in REMOVED:
        assert not list(g.triples((FB[t], None, None))), t
        assert not list(g.triples((None, None, FB[t]))), t


def test_every_property_has_label_comment_and_type():
    g = graph()
    props = set(g.subjects(RDF.type, OWL.ObjectProperty)) | set(g.subjects(RDF.type, OWL.DatatypeProperty))
    assert len(props) >= 45
    for p in props:
        assert (p, RDFS.label, None) in g, p
        assert (p, RDFS.comment, None) in g, p


def test_functional_and_inverse():
    g = graph()
    assert (FB.dateOfBirth, RDF.type, OWL.FunctionalProperty) in g
    assert (FB.hasPlayer, OWL.inverseOf, FB.playsFor) in g
