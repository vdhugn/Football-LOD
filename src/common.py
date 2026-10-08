"""Shared helpers: config, CSV reading, Turtle writing, value parsing, URIs."""
import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

csv.field_size_limit(10**7)

PREFIXES = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "schema": "https://schema.org/",
}

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ESC = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}
_NET = re.compile(r"^([+-]?)€([+-]?)([\d.]+)(bn|m|k)?$")
_MULT = {"bn": 10**9, "m": 10**6, "k": 10**3, None: 1}


# ---------- config / csv ----------

def load_config(path="config.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


# ---------- value parsing ----------

def clean(s):
    if s is None:
        return None
    s = _CTRL.sub("", s).strip()
    return s or None


def parse_date(s):
    s = clean(s)
    if s and re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    return None


def parse_int(s):
    s = clean(s)
    if s is None:
        return None
    try:
        return str(int(Decimal(s)))
    except (InvalidOperation, ValueError, OverflowError):
        return None


def parse_decimal(s):
    s = clean(s)
    if s is None:
        return None
    try:
        d = Decimal(s)
        if not d.is_finite():
            return None
        return format(d.normalize(), "f")
    except InvalidOperation:
        return None


def parse_net_transfer(s):
    s = clean(s)
    m = _NET.match(s) if s else None
    if not m:
        return None
    sign = -1 if "-" in (m.group(1), m.group(2)) else 1
    try:
        val = Decimal(m.group(3))
    except InvalidOperation:
        return None
    return str(int(sign * val * _MULT[m.group(4)]))


def slug(s):
    s = clean(s)
    return s.replace(" ", "_") if s else None


def hash_id(*parts):
    return hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:16]


# ---------- Turtle terms ----------

def esc(s):
    return "".join(_ESC.get(c, c) for c in s)


def lit(s, lang=None):
    s = clean(s) if s is not None else None
    if s is None:
        return None
    return f'"{esc(s)}"@{lang}' if lang else f'"{esc(s)}"'


def typed(v, dt):
    return None if v is None else f'"{v}"^^{dt}'


def t_int(s):
    return typed(parse_int(s), "xsd:integer")


def t_dec(s):
    return typed(parse_decimal(s), "xsd:decimal")


def t_date(s):
    return typed(parse_date(s), "xsd:date")


def iri(s):
    s = clean(s)
    if s is None or re.search(r'[\s<>"{}|\\^`]', s):
        return None
    return f"<{s}>"


class Uris:
    def __init__(self, cfg):
        self.base = cfg["resource_base"]
        self.onto = cfg["ontology_base"]

    def res(self, kind, key):
        key = clean(str(key)) if key is not None else None
        if key is None:
            return None
        return f"<{self.base}{kind}/{quote(key, safe='-_.~')}>"


class TurtleWriter:
    def __init__(self, path, ontology_base):
        self.path = Path(path)
        self.onto = ontology_base
        self.count = 0
        self.f = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "w", encoding="utf-8")
        for p, ns in PREFIXES.items():
            self.f.write(f"@prefix {p}: <{ns}> .\n")
        self.f.write(f"@prefix fb: <{self.onto}> .\n\n")
        return self

    def __exit__(self, *exc):
        self.f.close()

    def node(self, subject, *pairs):
        if subject is None:
            return
        parts = []
        for p, o in pairs:
            for x in (o if isinstance(o, list) else [o]):
                if x is not None:
                    parts.append((p, x))
        if not parts:
            return
        body = " ;\n    ".join(f"{p} {o}" for p, o in parts)
        self.f.write(f"{subject}\n    {body} .\n")
        self.count += len(parts)


@dataclass
class BuildCtx:
    cfg: dict
    uris: Uris
    scope: object
    data_dir: Path
    out_dir: Path
    notes: Counter = field(default_factory=Counter)
    seen: set = field(default_factory=set)
    countries: object = None

    def csv(self, name):
        return read_csv(Path(self.data_dir) / name)

    def writer(self, name):
        return TurtleWriter(Path(self.out_dir) / name, self.cfg["ontology_base"])

    def once(self, *key):
        if key in self.seen:
            return False
        self.seen.add(key)
        return True


def named_node(ctx, w, kind, cls, name):
    """Write a labelled reference node once per name; return its URI (or None)."""
    name = clean(name)
    if name is None:
        return None
    uri = ctx.uris.res(kind, slug(name))
    if ctx.once(kind, name):
        w.node(uri, ("a", cls), ("rdfs:label", lit(name, "und")))
    return uri
