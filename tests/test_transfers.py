from rdflib import Literal, URIRef
from rdflib.namespace import RDF, XSD

from builders import transfers
from common import hash_id
from helpers import FB, R, load_ttl


def uri(*parts):
    return URIRef(f"{R}transfer/{hash_id(*parts)}")


def test_fee_only_emitted_when_positive(ctx):
    transfers.build_transfers(ctx)
    g = load_ttl(ctx.out_dir / "transfers.ttl")
    fee = URIRef(FB + "transferFee")
    free = uri("10", "2019-07-01", "999", "11")             # fee "0.000"
    paid = uri("10", "2023-01-01", "11", "148")             # fee "5000000.000"
    blank = uri("10", "2024-01-01", "148", "11")            # fee ""
    assert not list(g.objects(free, fee))
    assert (paid, fee, Literal("5000000", datatype=XSD.decimal)) in g
    assert not list(g.objects(blank, fee))
    assert not any(o == Literal("0", datatype=XSD.decimal) for o in g.objects(None, fee))


def test_transfer_structure_and_duplicates(ctx):
    n = transfers.build_transfers(ctx)
    g = load_ttl(ctx.out_dir / "transfers.ttl")
    t = uri("10", "2023-01-01", "11", "148")
    assert (t, RDF.type, URIRef(FB + "Transfer")) in g
    assert (t, URIRef(FB + "transferOf"), URIRef(f"{R}player/10")) in g
    assert (t, URIRef(FB + "fromClub"), URIRef(f"{R}club/11")) in g
    assert (t, URIRef(FB + "toClub"), URIRef(f"{R}club/148")) in g
    assert (t, URIRef(FB + "transferDate"), Literal("2023-01-01", datatype=XSD.date)) in g
    assert (t, URIRef(FB + "marketValueAtTransferEUR"), Literal("90000000", datatype=XSD.decimal)) in g
    subjects = set(g.subjects(RDF.type, URIRef(FB + "Transfer")))
    assert len(subjects) == 3                                # duplicate row collapses; p30 excluded
    assert n >= len(g)                                       # duplicate row wrote the same triples twice


def test_valuations(ctx):
    transfers.build_valuations(ctx)
    g = load_ttl(ctx.out_dir / "valuations.ttl")
    v = URIRef(f"{R}valuation/10-2023-06-01")
    assert (v, RDF.type, URIRef(FB + "MarketValuation")) in g
    assert (v, URIRef(FB + "valuationOf"), URIRef(f"{R}player/10")) in g
    assert (v, URIRef(FB + "valueEUR"), Literal("100000000", datatype=XSD.decimal)) in g
    assert (v, URIRef(FB + "valuationDate"), Literal("2023-06-01", datatype=XSD.date)) in g
    assert (v, URIRef(FB + "atClub"), URIRef(f"{R}club/11")) in g
    old = URIRef(f"{R}valuation/10-2019-01-01")
    assert (old, URIRef(FB + "atClub"), URIRef(f"{R}club/999")) in g
    assert not list(g.triples((URIRef(f"{R}valuation/30-2020-01-01"), None, None)))   # out of scope
