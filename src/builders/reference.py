"""countries.csv, national_teams.csv, competitions.csv -> reference.ttl"""
from common import clean, iri, lit, named_node, t_dec, t_int


def build(ctx):
    u = ctx.uris
    with ctx.writer("reference.ttl") as w:
        for r in ctx.csv("countries.csv"):
            if not clean(r["country_id"]):
                continue
            w.node(u.res("country", r["country_id"]),
                   ("a", "fb:Country"),
                   ("rdfs:label", lit(r["country_name"], "en")),
                   ("fb:countryCode", lit(r["country_code"])),
                   ("fb:confederation", lit(r["confederation"])),
                   ("rdfs:seeAlso", iri(r["url"])))

        known = set()
        for r in ctx.csv("national_teams.csv"):
            nid = clean(r["national_team_id"])
            if not nid:
                continue
            known.add(nid)
            manager = named_node(ctx, w, "manager", "fb:Manager", r["coach_name"])
            w.node(u.res("national-team", nid),
                   ("a", "fb:NationalTeam"),
                   ("rdfs:label", lit(r["name"], "und")),
                   ("fb:country", u.res("country", clean(r["country_id"]))),
                   ("fb:confederation", lit(r["confederation"])),
                   ("fb:squadSize", t_int(r["squad_size"])),
                   ("fb:averageAge", t_dec(r["average_age"])),
                   ("fb:foreignersNumber", t_int(r["foreigners_number"])),
                   ("fb:foreignersPercentage", t_dec(r["foreigners_percentage"])),
                   ("fb:totalMarketValueEUR", t_dec(r["total_market_value"])),
                   ("fb:managedBy", manager),
                   ("fb:fifaRanking", t_int(r["fifa_ranking"])),
                   ("fb:lastSeason", t_int(r["last_season"])),
                   ("foaf:depiction", iri(r["team_image_url"])),
                   ("rdfs:seeAlso", iri(r["url"])))

        for nid in sorted(ctx.scope.national_ids - known):
            ctx.notes["national_team_minimal"] += 1
            w.node(u.res("national-team", nid),
                   ("a", "fb:NationalTeam"),
                   ("rdfs:label", lit(ctx.scope.national_names.get(nid), "und")))

        for r in ctx.csv("competitions.csv"):
            cid = clean(r["competition_id"])
            if not cid:
                continue
            country_id = clean(r["country_id"])
            country = u.res("country", country_id) if country_id and country_id != "-1" else None
            w.node(u.res("competition", cid),
                   ("a", "fb:Competition"),
                   ("rdfs:label", lit(r["name"], "und")),
                   ("fb:competitionCode", lit(r["competition_code"])),
                   ("fb:competitionType", lit(r["type"])),
                   ("fb:confederation", lit(r["confederation"])),
                   ("fb:country", country),
                   ("rdfs:seeAlso", iri(r["url"])))
    return w.count
