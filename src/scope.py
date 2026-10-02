"""Compute the in-scope game / club / national team / player ID sets."""
import json
from dataclasses import dataclass, field
from pathlib import Path

from common import clean, expand_seasons, read_csv


@dataclass
class Scope:
    game_ids: set = field(default_factory=set)
    game_kind: dict = field(default_factory=dict)
    club_ids: set = field(default_factory=set)
    club_names: dict = field(default_factory=dict)
    national_ids: set = field(default_factory=set)
    national_names: dict = field(default_factory=dict)
    player_ids: set = field(default_factory=set)

    def save(self, path):
        data = {
            "game_ids": sorted(self.game_ids), "game_kind": self.game_kind,
            "club_ids": sorted(self.club_ids), "club_names": self.club_names,
            "national_ids": sorted(self.national_ids), "national_names": self.national_names,
            "player_ids": sorted(self.player_ids),
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(set(d["game_ids"]), d["game_kind"], set(d["club_ids"]), d["club_names"],
                   set(d["national_ids"]), d["national_names"], set(d["player_ids"]))


def select_scope(cfg, data_dir):
    data_dir = Path(data_dir)
    comps = {c["id"]: (c["kind"], set(expand_seasons(c["seasons"]))) for c in cfg["competitions"]}
    s = Scope()

    def add_team(kind, tid, name):
        tid = clean(tid)
        if tid is None:
            return
        ids, names = (s.club_ids, s.club_names) if kind == "club" else (s.national_ids, s.national_names)
        ids.add(tid)
        name = clean(name)
        if name and name != "Unknown" and tid not in names:
            names[tid] = name

    for r in read_csv(data_dir / "games.csv"):
        spec = comps.get(r["competition_id"])
        if not spec or int(r["season"]) not in spec[1]:
            continue
        kind = spec[0]
        s.game_ids.add(r["game_id"])
        s.game_kind[r["game_id"]] = kind
        add_team(kind, r["home_club_id"], r["home_club_name"])
        add_team(kind, r["away_club_id"], r["away_club_name"])

    for r in read_csv(data_dir / "appearances.csv"):
        gid = r["game_id"]
        if gid in s.game_ids:
            s.player_ids.add(r["player_id"])
            add_team(s.game_kind[gid], r["player_club_id"], None)

    for r in read_csv(data_dir / "game_events.csv"):
        gid = r["game_id"]
        if gid in s.game_ids:
            for col in ("player_id", "player_in_id", "player_assist_id"):
                v = clean(r[col])
                if v:
                    s.player_ids.add(v)
            add_team(s.game_kind[gid], r["club_id"], r["club_name"])

    players = list(read_csv(data_dir / "players.csv"))
    for r in players:
        if clean(r["current_club_id"]) in s.club_ids:
            s.player_ids.add(r["player_id"])
    for r in players:
        if r["player_id"] in s.player_ids:
            add_team("club", r["current_club_id"], r["current_club_name"])

    for r in read_csv(data_dir / "transfers.csv"):
        if r["player_id"] in s.player_ids:
            add_team("club", r["from_club_id"], r["from_club_name"])
            add_team("club", r["to_club_id"], r["to_club_name"])

    for r in read_csv(data_dir / "player_valuations.csv"):
        if r["player_id"] in s.player_ids:
            add_team("club", r["current_club_id"], r["current_club_name"])

    return s
