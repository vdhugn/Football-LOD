import re

import pytest

from footballweb import create_app
from footballweb.ask import Asker, AskError, fold, label_pattern, parse_question
from footballweb.entities import Entities
from footballweb.sparqlutil import query_form
from helpers import FB, R

CFG = {"ontology_base": FB, "resource_base": R, "competitions": []}


def cand(kind, key, label):
    return {"s": {"type": "uri", "value": f"{R}{kind}/{key}"}, "label": {"type": "literal", "value": label},
            "type": {"type": "uri", "value": f"{FB}{ {'player': 'Player', 'club': 'Club', 'national-team': 'NationalTeam'}[kind] }"}}


def result(vars_, rows):
    return {"head": {"vars": vars_}, "results": {"bindings": rows}}


class Fake:
    """Answers entity-link queries from `names` (substring of the regex -> candidates)."""

    def __init__(self, names=None, final=None):
        self.names, self.final, self.queries = names or {}, final, []

    def select(self, q):
        self.queries.append(q)
        if "REGEX(" in q:
            plain = re.sub(r"\[(.)[^\]]*\]", r"\1", q.lower())       # undo the accent classes
            for needle, rows in self.names.items():
                if needle in plain:
                    return result(["s", "label", "type"], rows)
            return result(["s", "label", "type"], [])
        return self.final or result([], [])

    def ask(self, q):
        return True

    def construct(self, q):
        return ""


def asker(names=None, final=None):
    f = Fake(names, final)
    return Asker(f, CFG), f


# ---------- parsing ----------

def test_fold_strips_accents_and_case():
    assert fold("Kylian Mbappé  ÜBER") == "kylian mbappe uber"


def test_parse_scorers_with_competition_and_season():
    p = parse_question("Top scorers Premier League 2023")
    assert (p.intent, p.comp, p.season, p.limit) == ("scorers", "GB1", 2023, None)
    assert p.segments == [""]


@pytest.mark.parametrize("text,comp", [
    ("la liga top scorers", "ES1"), ("serie a top scorers", "IT1"), ("bundesliga scorers", "L1"),
    ("ligue 1 scorers", "FR1"), ("champions league scorers", "CL"), ("UEL scorers", "EL"),
    ("world cup scorers", "FIWC"),
])
def test_parse_competition_aliases(text, comp):
    assert parse_question(text).comp == comp


def test_parse_season_range_and_limit():
    p = parse_question("top 20 scorers 2022/23")
    assert (p.season, p.limit) == (2022, 20)


@pytest.mark.parametrize("text,intent", [
    ("most expensive transfers", "transfers"),
    ("arsenal squad", "players"),
    ("most valuable players", "players"),
    ("messi market value", "value"),
    ("messi stats", "stats"),
    ("how many goals did haaland score", "stats"),
    ("biggest wins champions league", "wins"),
    ("results of arsenal 2023", "matches"),
    ("top assists la liga", "assists"),
    ("messi", None),
])
def test_parse_intents(text, intent):
    assert parse_question(text).intent == intent


def test_parse_residual_drops_noise_words():
    assert parse_question("show me the squad of Manchester United").segments == ["manchester united"]


def test_parse_versus_splits_sides():
    p = parse_question("Arsenal vs Chelsea 2023")
    assert p.segments == ["arsenal", "chelsea"] and p.season == 2023


def test_parse_transfer_direction():
    assert parse_question("transfers to arsenal").direction == "to"
    assert parse_question("transfers from arsenal").direction == "from"
    assert parse_question("arsenal transfers").direction is None


def test_label_pattern_matches_accents_and_escapes():
    pattern = label_pattern("mbappe")
    assert "[eé" in pattern or "[eè" in pattern
    assert "." not in label_pattern("a.b")


# ---------- answering ----------

def test_scorers_query_is_built_from_template():
    a, _ = asker()
    r = a.ask("top scorers premier league 2023")
    assert r["intent"] == "scorers"
    assert f"<{R}competition/GB1>" in r["sparql"] and f"<{R}season/2023>" in r["sparql"]
    assert "LIMIT 10" in r["sparql"]
    assert "Premier League" in r["interpretation"] and "2023" in r["interpretation"]
    assert query_form(r["sparql"]) == "select"


def test_limit_is_capped():
    a, _ = asker()
    assert "LIMIT 100" in a.ask("top 500 scorers")["sparql"]


def test_squad_links_a_club():
    a, _ = asker({"arsenal": [cand("club", "11", "Arsenal FC"), cand("club", "9", "Arsenal Kyiv")]})
    r = a.ask("arsenal squad")
    assert r["intent"] == "players"
    assert f"fb:playsFor <{R}club/11>" in r["sparql"]
    assert "Arsenal FC" in r["interpretation"]


def test_exact_name_beats_query_order():
    a, _ = asker({"arsenal": [cand("club", "9", "Arsenal Kyiv"), cand("club", "11", "Arsenal FC")]})
    assert f"<{R}club/11>" in a.ask("arsenal squad")["sparql"]


def test_national_team_squad_uses_representation():
    a, _ = asker({"brazil": [cand("national-team", "3439", "Brazil")]})
    assert f"fb:representsNationalTeam <{R}national-team/3439>" in a.ask("players of brazil")["sparql"]


def test_value_history_needs_a_player():
    a, _ = asker({"messi": [cand("player", "28003", "Lionel Messi")]})
    r = a.ask("messi market value")
    assert f"fb:valuationOf <{R}player/28003>" in r["sparql"]
    with pytest.raises(AskError):
        asker({"arsenal": [cand("club", "11", "Arsenal FC")]})[0].ask("arsenal market value")


def test_unknown_player_is_reported():
    a, _ = asker()
    with pytest.raises(AskError) as e:
        a.ask("market value of zzzzqq")
    assert "zzzzqq" in str(e.value)


def test_transfers_direction_and_club():
    a, _ = asker({"arsenal": [cand("club", "11", "Arsenal FC")]})
    s = a.ask("transfers to arsenal")["sparql"]
    assert f"fb:toClub <{R}club/11>" in s and "fb:fromClub <" not in s
    both = a.ask("arsenal transfers")["sparql"]
    assert "fb:toClub|fb:fromClub" in both


def test_most_expensive_transfers_have_no_entity():
    s = asker()[0].ask("most expensive transfers")["sparql"]
    assert "ORDER BY DESC(?fee)" in s and "fb:transferFee ?fee" in s


def test_scorers_with_player_becomes_stats():
    a, _ = asker({"haaland": [cand("player", "418560", "Erling Haaland")]})
    r = a.ask("haaland goals premier league 2023")
    assert r["intent"] == "stats" and f"fb:appearanceOf <{R}player/418560>" in r["sparql"]
    assert f"<{R}competition/GB1>" in r["sparql"]


def test_scorers_for_a_club():
    a, _ = asker({"arsenal": [cand("club", "11", "Arsenal FC")]})
    s = a.ask("top scorers arsenal 2023")["sparql"]
    assert f"fb:forTeam <{R}club/11>" in s


def test_versus_finds_both_teams():
    a, _ = asker({"arsenal": [cand("club", "11", "Arsenal FC")], "chelsea": [cand("club", "631", "Chelsea FC")]})
    r = a.ask("arsenal vs chelsea")
    assert r["intent"] == "matches"
    assert f"<{R}club/11>" in r["sparql"] and f"<{R}club/631>" in r["sparql"]


def test_biggest_wins_with_competition():
    s = asker()[0].ask("biggest wins champions league")["sparql"]
    assert f"<{R}competition/CL>" in s and "ABS(?homeScore - ?awayScore)" in s


def test_bare_name_is_a_lookup():
    a, _ = asker({"messi": [cand("player", "28003", "Lionel Messi")]})
    r = a.ask("messi")
    assert r["intent"] == "lookup" and "REGEX(" in r["sparql"]


def test_unrecognised_gives_suggestions():
    a, _ = asker()
    with pytest.raises(AskError) as e:
        a.ask("tell me a joke")
    assert e.value.suggestions and len(e.value.suggestions) <= 3


def test_nearest_suggestion_is_relevant():
    a, _ = asker()
    with pytest.raises(AskError) as e:
        a.ask("scorrers in the premier leaguee")
    assert "scorers" in e.value.suggestions[0].lower()


def test_linked_uri_outside_the_namespace_is_ignored():
    bad = {"s": {"type": "uri", "value": "http://evil.example/x> } DROP"}, "label": {"type": "literal", "value": "Arsenal"},
           "type": {"type": "uri", "value": f"{FB}Club"}}
    a, _ = asker({"arsenal": [bad]})
    r = a.ask("arsenal squad")
    assert "evil" not in r["sparql"] and any("Ignored" in n for n in r["notes"])
    with pytest.raises(AskError):
        a.ask("arsenal market value")


def test_question_length_is_bounded():
    with pytest.raises(AskError):
        asker()[0].ask("x" * 500)
    with pytest.raises(AskError):
        asker()[0].ask("  ")


# ---------- table shaping and HTTP ----------

def test_answer_hides_uri_columns_and_links_labels():
    final = result(["player", "playerLabel", "goals"], [
        {"player": {"type": "uri", "value": f"{R}player/1"}, "playerLabel": {"type": "literal", "value": "A B"},
         "goals": {"type": "literal", "value": "1234", "datatype": "http://www.w3.org/2001/XMLSchema#integer"}}])
    a, _ = asker(final=final)
    out = a.answer("top scorers")
    assert out["vars"] == ["player", "goals"]
    assert out["rows"] == [[{"text": "A B", "href": "/page/player/1"}, {"text": "1,234", "href": None}]]
    assert out["truncated"] is False


def test_api_ask_endpoint():
    final = result(["playerLabel"], [{"playerLabel": {"type": "literal", "value": "Solo"}}])
    app = create_app(cfg=CFG, client=Fake(final=final))
    app.testing = True
    c = app.test_client()
    ok = c.post("/api/ask", json={"question": "top scorers premier league 2023"})
    assert ok.status_code == 200
    body = ok.get_json()
    assert body["vars"] == ["player"] and body["sparql"].startswith("PREFIX")
    bad = c.post("/api/ask", json={"question": "tell me a joke"})
    assert bad.status_code == 400 and bad.get_json()["suggestions"]
    assert c.post("/api/ask", json={}).status_code == 400
    assert c.post("/api/ask", data="x").status_code == 400


def test_pages_have_ask_box():
    app = create_app(cfg=CFG, client=Fake())
    app.testing = True
    c = app.test_client()
    assert b'id="ask"' in c.get("/query").data
    assert b'action="/query"' in c.get("/").data
