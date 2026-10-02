"""5-star linking: exact joins on Transfermarkt IDs against Wikidata, plus DBpedia and GeoNames.

CLI: python src/link_wikidata.py   (needs .cache/scope.json and output/data/*.ttl built)
Wikidata responses are cached under <cache_dir>/wikidata/, so reruns work offline.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from common import BuildCtx, TurtleWriter, Uris, clean, hash_id, load_config, read_csv, slug
from countries import CountryResolver
from scope import Scope

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "football-lod-course/0.1 (student project; contact via repository owner)"
WIKIDATA = "http://www.wikidata.org/entity/"
PROP_PLAYER, PROP_TEAM, PROP_COMPETITION = "P2446", "P7223", "P12758"


def sparql(query, retries=4):
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(ENDPOINT, data=data, headers={
        "Accept": "application/sparql-results+json", "User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = int(e.headers.get("Retry-After", 5 * 2 ** attempt))
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(5 * 2 ** attempt)
                continue
            raise


def cached_query(cache_dir, key, query, fetch=sparql, pause=1.0):
    path = Path(cache_dir) / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = fetch(query)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    time.sleep(pause)
    return result


def _rows(result):
    return [{k: v["value"] for k, v in b.items()} for b in result["results"]["bindings"]]


def tm_query(prop, ids, with_venue=False):
    values = " ".join(f'"{i}"' for i in ids)
    venue = ("OPTIONAL { ?item wdt:P115 ?venue . ?venue rdfs:label ?venueLabel . "
             'FILTER(LANG(?venueLabel) = "en") }' if with_venue else "")
    return (f"SELECT ?item ?tm ?article ?venue ?venueLabel WHERE {{ VALUES ?tm {{ {values} }} "
            f"?item wdt:{prop} ?tm . "
            "OPTIONAL { ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> } "
            f"{venue} }}")


def fetch_rows(prop, ids, cache_dir, key, fetch=sparql, with_venue=False, batch=300, pause=1.0):
    ids = sorted(ids)
    out, seen = [], set()
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        q = tm_query(prop, chunk, with_venue)
        result = cached_query(Path(cache_dir) / "wikidata", f"{key}-{hash_id(*chunk)}", q, fetch, pause)
        for row in _rows(result):
            sig = tuple(sorted(row.items()))
            if sig not in seen:
                seen.add(sig)
                out.append(row)
    return out


_IRI_UNSAFE = re.compile(r'[\x00-\x20<>"{}|^`\\%#?]')


def dbpedia_uri(article_url):
    """DBpedia resource IRIs use the decoded title (Kylian_Mbappé), not the percent-encoded URL path."""
    prefix = "https://en.wikipedia.org/wiki/"
    if not article_url or not article_url.startswith(prefix):
        return None
    title = urllib.parse.unquote(article_url[len(prefix):])
    return "http://dbpedia.org/resource/" + _IRI_UNSAFE.sub(lambda m: "%%%02X" % ord(m.group()), title)


def one_to_one(rows):
    """Keep only rows whose Transfermarkt ID <-> Wikidata item pair is unambiguous in both directions.

    Returns (kept_rows, number_of_ambiguous_transfermarkt_ids)."""
    items_of, ids_of = {}, {}
    for r in rows:
        items_of.setdefault(r["tm"], set()).add(r["item"])
        ids_of.setdefault(r["item"], set()).add(r["tm"])
    ok = {tm for tm, items in items_of.items()
          if len(items) == 1 and len(ids_of[next(iter(items))]) == 1}
    return [r for r in rows if r["tm"] in ok], len(items_of) - len(ok)


def write_links(out_dir, uris, kinds):
    out_dir = Path(out_dir)
    counts = {}
    with TurtleWriter(out_dir / "wikidata.ttl", uris.onto) as wd, \
            TurtleWriter(out_dir / "dbpedia.ttl", uris.onto) as db:
        for kind, rows in kinds.items():
            linked = set()
            for r in rows:
                ours = uris.res(kind, r["tm"])
                wd.node(ours, ("owl:sameAs", f"<{r['item']}>"))
                db_uri = dbpedia_uri(r.get("article"))
                db.node(ours, ("owl:sameAs", f"<{db_uri}>" if db_uri else None))
                linked.add(r["tm"])
            counts[kind] = len(linked)
    return counts


def write_stadium_links(out_dir, uris, club_rows, club_stadium_names):
    """club_rows: Wikidata rows for clubs (with venue); club_stadium_names: club id -> stadium name."""
    n = 0
    done = set()
    with TurtleWriter(Path(out_dir) / "stadiums.ttl", uris.onto) as w:
        for r in club_rows:
            ours_name = club_stadium_names.get(r["tm"])
            venue, label = r.get("venue"), r.get("venueLabel")
            if not (ours_name and venue and label):
                continue
            if clean(ours_name).casefold() != clean(label).casefold():
                continue
            key = (ours_name, venue)
            if key in done:
                continue
            done.add(key)
            w.node(uris.res("stadium", slug(ours_name)), ("skos:closeMatch", f"<{venue}>"))
            n += 1
    return n


def country_rows(names, cache_dir, fetch=sparql, pause=1.0):
    names = sorted(set(names))
    out = []
    for i in range(0, len(names), 100):
        chunk = names[i:i + 100]
        values = " ".join('"' + n.replace("\\", "\\\\").replace('"', '\\"') + '"@en' for n in chunk)
        q = ("SELECT ?name ?item ?geonames WHERE { VALUES ?name { " + values + " } "
             "?item rdfs:label ?name ; wdt:P31 ?type . VALUES ?type { wd:Q6256 wd:Q3624078 wd:Q3336843 } "
             "OPTIONAL { ?item wdt:P1566 ?geonames } }")
        result = cached_query(Path(cache_dir) / "wikidata", f"countries-{hash_id(q)}", q, fetch, pause)   # key covers the query text, not just the names
        for row in _rows(result):
            entry = {"name": row["name"], "item": row["item"],
                     **({"geonames": row["geonames"]} if "geonames" in row else {})}
            if entry not in out:     # an item matched through several P31 types appears twice
                out.append(entry)
    return out


def write_country_links(out_dir, rows, name_to_uri):
    n = 0
    done = set()
    with TurtleWriter(Path(out_dir) / "wikidata-countries.ttl", "") as wd, \
            TurtleWriter(Path(out_dir) / "geonames.ttl", "") as gn:
        for r in rows:
            ours = name_to_uri.get(r["name"])
            if ours is None or (ours, r["item"]) in done:
                continue
            done.add((ours, r["item"]))
            wd.node(ours, ("owl:sameAs", f"<{r['item']}>"))
            gn.node(ours, ("owl:sameAs", f"<https://sws.geonames.org/{r['geonames']}/>" if r.get("geonames") else None))
            n += 1
    return n


def write_report(out_dir, stats):
    rep = {}
    for k, (t, l, *extra) in stats.items():
        rep[k] = {"total": t, "linked": l, "rate": round(l / t, 4) if t else 0.0}
        if extra:
            rep[k]["ambiguous"] = extra[0]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    return rep


def main():
    cfg = load_config()
    scope = Scope.load(Path(cfg["cache_dir"]) / "scope.json")
    uris = Uris(cfg)
    cache = cfg["cache_dir"]
    out = Path(cfg["out_dir"]) / "links"
    data_dir = Path(cfg["data_dir"])

    nat_ids = {clean(r["national_team_id"]) for r in read_csv(data_dir / "national_teams.csv")} | scope.national_ids
    comp_ids = {c["id"] for c in cfg["competitions"]}

    players, amb_players = one_to_one(fetch_rows(PROP_PLAYER, scope.player_ids, cache, "player"))
    clubs, amb_clubs = one_to_one(fetch_rows(PROP_TEAM, scope.club_ids, cache, "club", with_venue=True))
    nationals, amb_nationals = one_to_one(fetch_rows(PROP_TEAM, nat_ids, cache, "national"))
    comps, amb_comps = one_to_one(fetch_rows(PROP_COMPETITION, comp_ids, cache, "competition"))

    counts = write_links(out, uris, {"player": players, "club": clubs,
                                     "national-team": nationals, "competition": comps})

    club_stadium = {clean(r["club_id"]): clean(r["stadium_name"])
                    for r in read_csv(data_dir / "clubs.csv") if clean(r["stadium_name"])}
    stadium_links = write_stadium_links(out, uris, clubs, club_stadium)

    ctx = BuildCtx(cfg, uris, scope, data_dir, out)
    resolver = CountryResolver(ctx)
    for r in read_csv(data_dir / "players.csv"):
        if r["player_id"] in scope.player_ids:
            resolver.uri(r["country_of_citizenship"])
            resolver.uri(r["country_of_birth"])
    names = resolver.lookup_names()
    crows = country_rows(list(names), cache)
    country_links = write_country_links(out, crows, names)

    report = write_report(out, {
        "player": (len(scope.player_ids), counts["player"], amb_players),
        "club": (len(scope.club_ids), counts["club"], amb_clubs),
        "national-team": (len(nat_ids), counts["national-team"], amb_nationals),
        "competition": (len(comp_ids), counts["competition"], amb_comps),
        "country": (len(resolver.all_names()), country_links),
        "stadium": (len(set(club_stadium.values())), stadium_links),
    })
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
