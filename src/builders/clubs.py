"""clubs.csv (+ scope) -> clubs.ttl"""
from common import clean, iri, lit, named_node, parse_net_transfer, t_dec, t_int, typed


def build(ctx):
    u = ctx.uris
    rows = {clean(r["club_id"]): r for r in ctx.csv("clubs.csv")}
    with ctx.writer("clubs.ttl") as w:
        for cid in sorted(ctx.scope.club_ids):
            uri = u.res("club", cid)
            r = rows.get(cid)
            if r is None:
                ctx.notes["club_minimal"] += 1
                w.node(uri, ("a", "fb:Club"), ("rdfs:label", lit(ctx.scope.club_names.get(cid), "und")))
                continue
            stadium = named_node(ctx, w, "stadium", "fb:Stadium", r["stadium_name"])
            if stadium:
                w.node(stadium, ("fb:stadiumSeats", t_int(r["stadium_seats"])))
            manager = named_node(ctx, w, "manager", "fb:Manager", r["coach_name"])
            comp = clean(r["domestic_competition_id"])
            w.node(uri,
                   ("a", "fb:Club"),
                   ("rdfs:label", lit(r["name"], "und")),
                   ("fb:domesticCompetition", u.res("competition", comp) if comp else None),
                   ("fb:squadSize", t_int(r["squad_size"])),
                   ("fb:averageAge", t_dec(r["average_age"])),
                   ("fb:foreignersNumber", t_int(r["foreigners_number"])),
                   ("fb:foreignersPercentage", t_dec(r["foreigners_percentage"])),
                   ("fb:nationalTeamPlayers", t_int(r["national_team_players"])),
                   ("fb:totalMarketValueEUR", t_dec(r["total_market_value"])),
                   ("fb:netTransferRecordEUR", typed(parse_net_transfer(r["net_transfer_record"]), "xsd:decimal")),
                   ("fb:homeStadium", stadium),
                   ("fb:managedBy", manager),
                   ("fb:lastSeason", t_int(r["last_season"])),
                   ("rdfs:seeAlso", iri(r["url"])))
    return w.count
