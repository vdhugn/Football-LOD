"""CLI: python src/build_rdf.py [--config config.json]  (needs .cache/scope.json)"""
import argparse
from pathlib import Path

from builders import clubs, players, reference, transfers
from common import BuildCtx, Uris, load_config
from scope import Scope

STEPS = [
    ("reference.ttl", reference.build),
    ("clubs.ttl", clubs.build),
    ("players.ttl", players.build),
    ("transfers.ttl", transfers.build_transfers),
    ("valuations.ttl", transfers.build_valuations),
]


def run(cfg, scope, data_dir, out_dir):
    out_dir = Path(out_dir)
    ctx = BuildCtx(cfg, Uris(cfg), scope, Path(data_dir), out_dir / "data")
    totals = {}
    for name, build in STEPS:
        totals[name] = build(ctx)
        print(f"{name:18s} {totals[name]:>12,d} triples")
    print(f"{'TOTAL':18s} {sum(totals.values()):>12,d} triples")
    for key, n in sorted(ctx.notes.items()):
        print(f"note: {key} = {n:,d}")
    return totals


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    scope = Scope.load(Path(cfg["cache_dir"]) / "scope.json")
    run(cfg, scope, cfg["data_dir"], cfg["out_dir"])


if __name__ == "__main__":
    main()
