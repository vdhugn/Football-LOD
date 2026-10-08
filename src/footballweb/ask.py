"""Plain-language questions: rule-based intent matching, entity linking and SPARQL templates.

Everything runs offline in this process; the only outside call is the label lookup in Fuseki
used to link names such as "arsenal" or "mbappe" to resources.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .entities import NUMERIC, Entities, fmt_number, short
from .sparqlutil import escape_literal

MAX_QUESTION_CHARS = 200
MAX_LIMIT = 100
MAX_ROWS = 1000
DEFAULT_LIMIT = {"transfers": 10, "players": 20, "value": 50, "lookup": 20}

COMPETITIONS = [
    ("english premier league", "GB1"), ("premier league", "GB1"), ("epl", "GB1"),
    ("la liga", "ES1"), ("laliga", "ES1"), ("serie a", "IT1"), ("bundesliga", "L1"), ("ligue 1", "FR1"),
]
COMPETITIONS.sort(key=lambda a: -len(a[0]))
COMP_NAMES = {"GB1": "Premier League", "ES1": "La Liga", "IT1": "Serie A", "L1": "Bundesliga",
              "FR1": "Ligue 1"}

# first match wins; strong "players" patterns come before "value" so that
# "most valuable players by market value" is a list of players, not one player's history
INTENTS = [
    ("transfers", r"\btransfers?\b|\bsigned\b|\bsold\b|\bbought\b|\bsignings?\b"),
    ("players", r"\bmost valuable\b|\bhighest valued\b|\bmost expensive players\b|\bsquad\b|\broster\b"),
    ("value", r"\bvaluations?\b|\bworth\b|\bmarket value\b|\bvalue history\b|\bhow much\b"),
    ("players", r"\bplayers?\b"),
]
STOP = set("""the a an of in at for by to from and or show me list give get find what which who whom is are was were
did do does how many much all top best most biggest largest highest record win wins victory victories margin margins
scorer scorers goalscorer goalscorers goal goals assist assists transfer transfers expensive valuable value values
valuation valuations worth market history squad players player roster team club clubs results result matches match
games game fixtures fixture score scores stats stat statistics career appearances appearance season league please
with on his her their has have had scored scoring signed signing sold bought joined played plays playing current
now latest recent last first new ever overall total tell about i want see between into""".split())
AFFIXES = {"fc", "cf", "afc", "sc", "ac", "ssc"}

EXAMPLES = [
    "Most valuable players Premier League", "Most expensive transfers", "Arsenal squad",
    "Haaland market value", "Players of Brazil", "Transfers to Arsenal",
    "Mbappe valuation history", "Transfers from Real Madrid 2023", "Most valuable players",
]

_ACCENTS = {"a": "àáâãäåāăą", "e": "èéêëēėę", "i": "ìíîïī", "o": "òóôõöøō", "u": "ùúûüū", "c": "çćč",
            "n": "ñń", "s": "śšß", "z": "źżž", "y": "ýÿ", "l": "ł", "d": "đð", "g": "ğ", "t": "ț"}


class AskError(Exception):
    def __init__(self, message, suggestions=()):
        super().__init__(message)
        self.suggestions = list(suggestions)


def fold(text):
    """Lower-case, accent-free, single-spaced."""
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.lower()).strip()


def label_pattern(phrase):
    """Regex (Java flavour, case-insensitive) that finds `phrase` in labels whatever their accents."""
    clean = re.sub(r"[^a-z0-9 ]", "", fold(phrase))
    parts = []
    for c in clean:
        if c == " ":
            parts.append("[ -]")
        elif c in _ACCENTS:
            parts.append(f"[{c}{_ACCENTS[c]}]")
        else:
            parts.append(c)
    return r"\b" + "".join(parts)


def _core(text):
    return " ".join(t for t in re.sub(r"[^a-z0-9 ]", " ", fold(text)).split() if t not in AFFIXES)


@dataclass
class Parsed:
    intent: str | None
    comp: str | None = None
    season: int | None = None
    limit: int | None = None
    direction: str | None = None
    segments: list = field(default_factory=list)
    versus: bool = False


def parse_question(text):
    t = " " + fold(text) + " "
    comp = season = limit = None
    for alias, code in COMPETITIONS:
        pat = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
        if re.search(pat, t):
            comp, t = code, re.sub(pat, " ", t, count=1)
            break
    m = re.search(r"\b(?:top|first|best)\s+(\d{1,4})\b", t)
    if m and not 1900 <= int(m.group(1)) <= 2100:
        limit, t = min(int(m.group(1)), MAX_LIMIT), t[:m.start()] + " " + t[m.end():]
    m = re.search(r"\b((?:19|20)\d\d)(?:\s*[/-]\s*(?:\d{4}|\d{2}))?\b", t)
    if m:
        season, t = int(m.group(1)), t[:m.start()] + " " + t[m.end():]
    direction = None
    if re.search(r"\b(?:from|sold|left)\b", t) and not re.search(r"\b(?:to|into|bought|signed|joined)\b", t):
        direction = "from"
    elif re.search(r"\b(?:to|into|bought|signed|joined)\b", t) and not re.search(r"\b(?:from|sold|left)\b", t):
        direction = "to"
    intent = next((name for name, pat in INTENTS if re.search(pat, t)), None)
    sides = re.split(r"\b(?:vs|v|versus|against)\b", t)
    segments = [" ".join(w for w in re.sub(r"[^a-z0-9' -]", " ", s).split() if w not in STOP and not w.isdigit())
                for s in sides]
    return Parsed(intent, comp, season, limit, direction, segments, versus=len(sides) > 1)


class Asker:
    def __init__(self, client, cfg):
        self.client = client
        self.ent = Entities(client, cfg)
        self.base = cfg["resource_base"]

    # ---------- entity linking ----------

    def _candidates(self, phrase):
        pattern = escape_literal(label_pattern(phrase))
        q = (self.ent.prefixes +
             "SELECT ?s ?label ?type WHERE { VALUES ?type { fb:Player fb:Club fb:NationalTeam } "
             "?s a ?type ; rdfs:label ?label . OPTIONAL { ?s fb:homeStadium ?st } "
             "OPTIONAL { ?s fb:currentMarketValueEUR ?val } "
             f'FILTER(REGEX(STR(?label), "{pattern}", "i")) }} '
             "ORDER BY DESC(BOUND(?st)) DESC(COALESCE(?val, 0)) STRLEN(?label) LIMIT 30")
        out = []
        for b in self.client.select(q)["results"]["bindings"]:
            uri = b["s"]["value"]
            if uri.startswith(self.base) and re.fullmatch(r"[^<>\s\"{}|^`\\]+", uri):
                out.append({"uri": uri, "label": b["label"]["value"], "type": short(b["type"]["value"]),
                            "href": self.ent.local(uri)})
        want = _core(phrase)
        out.sort(key=lambda c: _core(c["label"]) != want)     # stable: exact names first, then Fuseki's order
        return out

    def _link(self, segment, partial=True):
        tokens = segment.split()[:6]
        for size in range(len(tokens), 0, -1):
            if size < len(tokens) and not partial:
                break
            for start in range(len(tokens) - size + 1):
                phrase = " ".join(tokens[start:start + size])
                if len(phrase) >= 3:
                    found = self._candidates(phrase)
                    if found:
                        return phrase, found
        return None

    # ---------- public API ----------

    def ask(self, text):
        text = (text or "").strip()
        if not text:
            raise AskError("Type a question, for example “most valuable players Premier League”.", EXAMPLES[:3])
        if len(text) > MAX_QUESTION_CHARS:
            raise AskError(f"The question is longer than {MAX_QUESTION_CHARS} characters.", EXAMPLES[:3])
        p = parse_question(text)
        notes, entities = [], []
        strict = p.intent in ("lookup", "value", None) or p.versus
        for seg in p.segments:
            if not seg:
                continue
            hit = self._link(seg, partial=p.intent is not None)
            if hit:
                phrase, found = hit
                entities.append(found[0])
                others = [c["label"] for c in found[1:4] if c["label"] != found[0]["label"]]
                if others and _core(found[0]["label"]) != _core(phrase):
                    notes.append(f"“{phrase}” also matches: {', '.join(others)}.")
            elif strict:
                raise AskError(f"I could not find a player, club or national team matching “{seg}”.",
                               self._suggest(text))
            else:
                notes.append(f"Ignored “{seg}”: no matching player or team.")
        intent = p.intent or ("lookup" if entities else None)
        if intent is None:
            raise AskError("I did not understand that question.", self._suggest(text))
        players = [e for e in entities if e["type"] == "Player"]
        teams = [e for e in entities if e["type"] != "Player"]
        build = getattr(self, f"_q_{intent}")
        sparql, meaning = build(p, players, teams, entities)
        return {"question": text, "intent": intent, "interpretation": meaning, "sparql": sparql,
                "notes": notes, "entities": [{"label": e["label"], "type": e["type"], "href": e["href"]} for e in entities]}

    def answer(self, text):
        out = self.ask(text)
        res = self.client.select(out["sparql"])
        out.update(self._tabulate(res))
        return out

    def _suggest(self, text):
        q = fold(text).split()
        def score(example):
            et = fold(example).split()
            return sum(max(SequenceMatcher(None, w, e).ratio() for e in et) for w in q) / max(len(q), 1)
        return sorted(EXAMPLES, key=score, reverse=True)[:3]

    # ---------- result table ----------

    def _tabulate(self, res):
        names = res["head"]["vars"]
        hidden = {n for n in names if f"{n}Label" in names}
        cols = [n for n in names if n not in hidden]
        rows = []
        for b in res["results"]["bindings"][:MAX_ROWS]:
            row = []
            for n in cols:
                cell = b.get(n)
                if cell is None:
                    row.append(None)
                    continue
                href = None
                if n.endswith("Label") and n[:-5] in b:
                    href = self.ent.local(b[n[:-5]]["value"])
                dt = short(cell["datatype"]) if cell.get("datatype") else None
                text = fmt_number(cell["value"]) if dt in NUMERIC else cell["value"]
                row.append({"text": text, "href": href})
            rows.append(row)
        return {"vars": [n[:-5] if n.endswith("Label") else n for n in cols], "rows": rows,
                "truncated": len(res["results"]["bindings"]) > MAX_ROWS}

    # ---------- SPARQL templates ----------

    def _limit(self, p, intent):
        return p.limit or DEFAULT_LIMIT[intent]

    def _iri(self, uri):
        return f"<{uri}>"

    def _year(self, p, var="?date"):
        return [f"FILTER(YEAR({var}) = {p.season})"] if p.season else []

    def _select(self, head, body, tail):
        return self.ent.prefixes + f"SELECT {head} WHERE {{\n  " + "\n  ".join(body) + f"\n}} {tail}"

    def _need_player(self, players, what):
        if not players:
            raise AskError(f"{what} needs a player name, for example “Haaland market value”.", EXAMPLES[3:4] + EXAMPLES[6:7])
        return players[0]

    def _q_transfers(self, p, players, teams, entities):
        body = ["?t fb:transferOf ?player ; fb:transferDate ?date ; fb:fromClub ?from ; fb:toClub ?to ."]
        n = self._limit(p, "transfers")
        what = "Transfers"
        if players:
            body.insert(0, f"VALUES ?player {{ {self._iri(players[0]['uri'])} }}")
            body.append("OPTIONAL { ?t fb:transferFee ?fee }")
            order, what = "ORDER BY DESC(?date)", f"Transfers of {players[0]['label']}"
        else:
            body.append("?t fb:transferFee ?fee .")
            order, what = "ORDER BY DESC(?fee)", f"Top {n} most expensive transfers"
        if teams:
            club = self._iri(teams[0]["uri"])
            path = {"to": "fb:toClub", "from": "fb:fromClub"}.get(p.direction, "fb:toClub|fb:fromClub")
            body.append(f"?t {path} {club} .")
            what += {"to": " to ", "from": " from "}.get(p.direction, " involving ") + teams[0]["label"]
        body += self._year(p)
        if p.season:
            what += f" in {p.season}"
        body += ["OPTIONAL { ?player rdfs:label ?playerLabel }", "OPTIONAL { ?from rdfs:label ?fromLabel }",
                 "OPTIONAL { ?to rdfs:label ?toLabel }"]
        sparql = self._select("?date ?player ?playerLabel ?from ?fromLabel ?to ?toLabel ?fee", body, f"{order} LIMIT {n}")
        return sparql, what

    def _q_players(self, p, players, teams, entities):
        body = ["?player a fb:Player ; rdfs:label ?playerLabel ."]
        what = "Most valuable players"
        if teams:
            prop = "fb:representsNationalTeam" if teams[0]["type"] == "NationalTeam" else "fb:playsFor"
            body.append(f"?player {prop} {self._iri(teams[0]['uri'])} .")
            what += f" of {teams[0]['label']} (current squad)"
        if p.comp:
            body.append(f"?player fb:playsFor ?club . ?club fb:domesticCompetition {self.ent.iri('competition', p.comp)} .")
            what += f" · {COMP_NAMES[p.comp]}"
        body.append("OPTIONAL { ?player fb:currentMarketValueEUR ?value }")
        n = self._limit(p, "players")
        return self._select("?player ?playerLabel ?value", body, f"ORDER BY DESC(?value) LIMIT {n}"), what

    def _q_value(self, p, players, teams, entities):
        player = self._need_player(players, "Market value history")
        body = [f"?v fb:valuationOf {self._iri(player['uri'])} ; fb:valuationDate ?date ; fb:valueEUR ?value ."]
        body += self._year(p)
        body.append("OPTIONAL { ?v fb:atClub ?club . OPTIONAL { ?club rdfs:label ?clubLabel } }")
        n = self._limit(p, "value")
        what = f"Market value history of {player['label']}" + (f" in {p.season}" if p.season else "")
        return self._select("?date ?value ?club ?clubLabel", body, f"ORDER BY DESC(?date) LIMIT {n}"), what

    def _q_lookup(self, p, players, teams, entities):
        phrase = " ".join(p.segments).strip()
        pattern = escape_literal(label_pattern(phrase))
        sparql = (self.ent.prefixes +
                  "SELECT ?entity ?entityLabel (STRAFTER(STR(?type), \"#\") AS ?kind) WHERE {\n"
                  "  VALUES ?type { fb:Player fb:Club fb:NationalTeam fb:Competition }\n"
                  "  ?entity a ?type ; rdfs:label ?entityLabel .\n"
                  "  OPTIONAL { ?entity fb:homeStadium ?st } OPTIONAL { ?entity fb:currentMarketValueEUR ?val }\n"
                  f'  FILTER(REGEX(STR(?entityLabel), "{pattern}", "i"))\n}} '
                  "ORDER BY DESC(BOUND(?st)) DESC(COALESCE(?val, 0)) STRLEN(?entityLabel) LIMIT 20")
        return sparql, f"Resources named “{phrase}”"
