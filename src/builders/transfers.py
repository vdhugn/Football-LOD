"""transfers.csv -> transfers.ttl ; player_valuations.csv -> valuations.ttl"""
from common import clean, hash_id, lit, parse_date, parse_decimal, t_dec, t_date, typed


def build_transfers(ctx):
    u = ctx.uris
    with ctx.writer("transfers.ttl") as w:
        for r in ctx.csv("transfers.csv"):
            pid = clean(r["player_id"])
            if pid not in ctx.scope.player_ids:
                continue
            date, frm, to = parse_date(r["transfer_date"]), clean(r["from_club_id"]), clean(r["to_club_id"])
            fee = parse_decimal(r["transfer_fee"])
            fee = fee if fee is not None and float(fee) > 0 else None
            w.node(u.res("transfer", hash_id(pid, date, frm, to)),
                   ("a", "fb:Transfer"),
                   ("fb:transferOf", u.res("player", pid)),
                   ("fb:fromClub", u.res("club", frm)),
                   ("fb:toClub", u.res("club", to)),
                   ("fb:transferDate", t_date(r["transfer_date"])),
                   ("fb:transferSeason", lit(r["transfer_season"])),
                   ("fb:transferFee", typed(fee, "xsd:decimal")),
                   ("fb:marketValueAtTransferEUR", t_dec(r["market_value_in_eur"])))
    return w.count


def build_valuations(ctx):
    u = ctx.uris
    with ctx.writer("valuations.ttl") as w:
        for r in ctx.csv("player_valuations.csv"):
            pid = clean(r["player_id"])
            date = parse_date(r["date"])
            if pid not in ctx.scope.player_ids or date is None:
                continue
            w.node(u.res("valuation", f"{pid}-{date}"),
                   ("a", "fb:MarketValuation"),
                   ("fb:valuationOf", u.res("player", pid)),
                   ("fb:valuationDate", t_date(r["date"])),
                   ("fb:valueEUR", t_dec(r["market_value_in_eur"])),
                   ("fb:atClub", u.res("club", clean(r["current_club_id"]))))
    return w.count
