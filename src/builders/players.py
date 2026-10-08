"""players.csv (+ scope) -> players.ttl (also positions and non-listed countries)"""
from common import clean, iri, lit, slug, t_date, t_dec, t_int
from countries import CountryResolver


def _position(ctx, w, name, broader=None):
    name = clean(name)
    if name is None or name == "Missing":
        return None
    uri = ctx.uris.res("position", slug(name))
    if ctx.once("position", name):
        w.node(uri, ("a", ["fb:Position", "skos:Concept"]),
               ("rdfs:label", lit(name, "en")),
               ("skos:broader", broader))
    return uri


def build(ctx):
    u = ctx.uris
    ctx.countries = countries = CountryResolver(ctx)
    national_ids = {clean(r["national_team_id"]) for r in ctx.csv("national_teams.csv")}
    seen_players = set()
    with ctx.writer("players.ttl") as w:
        for r in ctx.csv("players.csv"):
            pid = clean(r["player_id"])
            if pid not in ctx.scope.player_ids:
                continue
            seen_players.add(pid)
            position = _position(ctx, w, r["position"])
            sub = _position(ctx, w, r["sub_position"], broader=position)
            nat = clean(r["current_national_team_id"])
            w.node(u.res("player", pid),
                   ("a", "fb:Player"),
                   ("rdfs:label", lit(r["name"], "und")),
                   ("fb:firstName", lit(r["first_name"], "und")),
                   ("fb:lastName", lit(r["last_name"], "und")),
                   ("fb:dateOfBirth", t_date(r["date_of_birth"])),
                   ("fb:bornIn", countries.uri(r["country_of_birth"])),
                   ("fb:birthCity", lit(r["city_of_birth"])),
                   ("fb:citizenOf", countries.uri(r["country_of_citizenship"])),
                   ("fb:position", position),
                   ("fb:subPosition", sub),
                   ("fb:preferredFoot", lit(r["foot"])),
                   ("fb:heightCm", t_int(r["height_in_cm"])),
                   ("fb:currentMarketValueEUR", t_dec(r["market_value_in_eur"])),
                   ("fb:highestMarketValueEUR", t_dec(r["highest_market_value_in_eur"])),
                   ("fb:playsFor", u.res("club", clean(r["current_club_id"]))),
                   ("fb:representsNationalTeam", u.res("national-team", nat) if nat in national_ids else None),
                   ("fb:internationalCaps", t_int(r["international_caps"])),
                   ("fb:internationalGoals", t_int(r["international_goals"])),
                   ("fb:contractExpires", t_date(r["contract_expiration_date"])),
                   ("fb:agent", lit(r["agent_name"])),
                   ("foaf:depiction", iri(r["image_url"])),
                   ("rdfs:seeAlso", iri(r["url"])))
        for pid in sorted(ctx.scope.player_ids - seen_players):
            ctx.notes["player_minimal"] += 1
            w.node(u.res("player", pid), ("a", "fb:Player"))
        countries.write_extra(w)
    return w.count
