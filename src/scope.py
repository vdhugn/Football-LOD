"""Compute the in-scope club / player ID sets.

Clubs: clubs.csv rows whose domestic league is in cfg["scope"]["leagues"] and whose last_season
is cfg["scope"]["season"]. Players: players.csv rows whose current club is one of those clubs and
whose last_season is that season. Clubs met in those players' transfers and valuations are added
so that every club reference resolves (most of them become minimal nodes).
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from common import clean, read_csv


@dataclass
class Scope:
    club_ids: set = field(default_factory=set)
    club_names: dict = field(default_factory=dict)
    player_ids: set = field(default_factory=set)

    def save(self, path):
        data = {"club_ids": sorted(self.club_ids), "club_names": self.club_names,
                "player_ids": sorted(self.player_ids)}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(set(d["club_ids"]), d["club_names"], set(d["player_ids"]))


def _season(value):
    v = clean(value)
    return int(v) if v and v.isdigit() else None


def select_scope(cfg, data_dir):
    data_dir = Path(data_dir)
    leagues, season = set(cfg["scope"]["leagues"]), int(cfg["scope"]["season"])
    s = Scope()

    def add_club(cid, name):
        cid = clean(cid)
        if cid is None:
            return
        s.club_ids.add(cid)
        name = clean(name)
        if name and name != "Unknown" and cid not in s.club_names:
            s.club_names[cid] = name

    core = set()
    for r in read_csv(data_dir / "clubs.csv"):
        if clean(r["domestic_competition_id"]) in leagues and _season(r["last_season"]) == season:
            core.add(clean(r["club_id"]))
            add_club(r["club_id"], r["name"])

    for r in read_csv(data_dir / "players.csv"):
        if clean(r["current_club_id"]) in core and _season(r["last_season"]) == season:
            s.player_ids.add(clean(r["player_id"]))

    for r in read_csv(data_dir / "transfers.csv"):
        if clean(r["player_id"]) in s.player_ids:
            add_club(r["from_club_id"], r["from_club_name"])
            add_club(r["to_club_id"], r["to_club_name"])

    for r in read_csv(data_dir / "player_valuations.csv"):
        if clean(r["player_id"]) in s.player_ids:
            add_club(r["current_club_id"], r["current_club_name"])

    return s
