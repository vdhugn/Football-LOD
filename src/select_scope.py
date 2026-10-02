"""CLI: python src/select_scope.py [--config config.json]  ->  <cache_dir>/scope.json"""
import argparse
from pathlib import Path

from common import load_config
from scope import select_scope


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    scope = select_scope(cfg, cfg["data_dir"])
    out = Path(cfg["cache_dir"]) / "scope.json"
    scope.save(out)
    print(f"games={len(scope.game_ids)} clubs={len(scope.club_ids)} "
          f"national_teams={len(scope.national_ids)} players={len(scope.player_ids)} -> {out}")


if __name__ == "__main__":
    main()
