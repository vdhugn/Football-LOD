"""appearances.csv -> appearances.ttl ; game_events.csv -> events.ttl"""
import re

from common import clean, lit, t_int, typed

EVENT_CLASS = {
    "Goals": "fb:Goal",
    "Cards": "fb:Card",
    "Substitutions": "fb:Substitution",
    "Shootout": "fb:PenaltyShootoutKick",
}


def split_description(desc):
    desc = clean(desc)
    if desc is None:
        return None, None
    head, _, tail = desc.partition(",")
    return clean(head), clean(tail)


def build_appearances(ctx):
    u = ctx.uris
    with ctx.writer("appearances.ttl") as w:
        for r in ctx.csv("appearances.csv"):
            gid = r["game_id"]
            if gid not in ctx.scope.game_ids:
                continue
            kind = ctx.scope.game_kind[gid]
            w.node(u.res("appearance", r["appearance_id"]),
                   ("a", "fb:Appearance"),
                   ("fb:appearanceOf", u.res("player", r["player_id"])),
                   ("fb:inMatch", u.res("match", gid)),
                   ("fb:forTeam", u.team(kind, r["player_club_id"])),
                   ("fb:goals", t_int(r["goals"])),
                   ("fb:assists", t_int(r["assists"])),
                   ("fb:minutesPlayed", t_int(r["minutes_played"])),
                   ("fb:yellowCards", t_int(r["yellow_cards"])),
                   ("fb:redCards", t_int(r["red_cards"])))
    return w.count


def build_events(ctx):
    u = ctx.uris
    with ctx.writer("events.ttl") as w:
        for r in ctx.csv("game_events.csv"):
            gid = r["game_id"]
            if gid not in ctx.scope.game_ids:
                continue
            typ = r["type"]
            cls = EVENT_CLASS.get(typ)
            if cls is None:
                ctx.notes["event_unknown_type"] += 1
                continue
            kind = ctx.scope.game_kind[gid]
            head, tail = split_description(r["description"])
            player = u.res("player", clean(r["player_id"]))
            card_type = re.sub(r"^\d+\.\s*", "", head) if typ == "Cards" and head else None
            scored = None
            if typ == "Shootout" and tail:
                scored = typed("true" if tail.lower().startswith("scored") else "false", "xsd:boolean")
            w.node(u.res("event", r["game_event_id"]),
                   ("a", cls),
                   ("fb:inMatch", u.res("match", gid)),
                   ("fb:minute", t_int(r["minute"])),
                   ("fb:forTeam", u.team(kind, r["club_id"])),
                   ("fb:byPlayer", player),
                   ("fb:assistedBy", u.res("player", clean(r["player_assist_id"])) if typ == "Goals" else None),
                   ("fb:playerOut", player if typ == "Substitutions" else None),
                   ("fb:playerIn", u.res("player", clean(r["player_in_id"])) if typ == "Substitutions" else None),
                   ("fb:cardType", lit(card_type)),
                   ("fb:scored", scored),
                   ("rdfs:comment", lit(tail)))
    return w.count
