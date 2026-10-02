"""games.csv -> matches.ttl"""
from common import clean, iri, lit, named_node, t_date, t_int


def build(ctx):
    u = ctx.uris
    with ctx.writer("matches.ttl") as w:
        for r in ctx.csv("games.csv"):
            gid = r["game_id"]
            if gid not in ctx.scope.game_ids:
                continue
            kind = ctx.scope.game_kind[gid]
            home, away = u.team(kind, r["home_club_id"]), u.team(kind, r["away_club_id"])
            if home is None or away is None:
                ctx.notes["match_missing_team"] += 1
            season = clean(r["season"])
            season_uri = u.res("season", season)
            if season_uri and ctx.once("season", season):
                w.node(season_uri, ("a", "fb:Season"),
                       ("rdfs:label", lit(f"Season {season}")),
                       ("fb:startYear", t_int(season)))
            stadium = named_node(ctx, w, "stadium", "fb:Stadium", r["stadium"])
            referee = named_node(ctx, w, "referee", "fb:Referee", r["referee"])
            hn, an = clean(r["home_club_name"]), clean(r["away_club_name"])
            label = f"{hn} vs {an}" if hn and an else None
            w.node(u.res("match", gid),
                   ("a", "fb:Match"),
                   ("rdfs:label", lit(label, "und")),
                   ("fb:inCompetition", u.res("competition", clean(r["competition_id"]))),
                   ("fb:inSeason", season_uri),
                   ("fb:matchDate", t_date(r["date"])),
                   ("fb:round", lit(r["round"])),
                   ("fb:homeTeam", home),
                   ("fb:awayTeam", away),
                   ("fb:homeScore", t_int(r["home_club_goals"])),
                   ("fb:awayScore", t_int(r["away_club_goals"])),
                   ("fb:hostedAt", stadium),
                   ("fb:attendance", t_int(r["attendance"])),
                   ("fb:refereedBy", referee),
                   ("fb:homeFormation", lit(r["home_club_formation"])),
                   ("fb:awayFormation", lit(r["away_club_formation"])),
                   ("rdfs:seeAlso", iri(r["url"])))
    return w.count
