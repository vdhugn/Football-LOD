"""Resolve country names (as used in players.csv) to country URIs."""
from common import clean, lit, slug

ALIASES = {"Turkey": "Türkiye"}


class CountryResolver:
    def __init__(self, ctx):
        self.uris = ctx.uris
        self.by_name = {}
        for r in ctx.csv("countries.csv"):
            name, cid = clean(r["country_name"]), clean(r["country_id"])
            if name and cid:
                self.by_name[name] = self.uris.res("country", cid)
        self.extra = {}

    def uri(self, name):
        name = clean(name)
        if name is None:
            return None
        name = ALIASES.get(name, name)
        if name in self.by_name:
            return self.by_name[name]
        if name not in self.extra:
            self.extra[name] = self.uris.res("country", "n-" + slug(name))
        return self.extra[name]

    def all_names(self):
        return {**self.by_name, **self.extra}

    def write_extra(self, w):
        for name, uri in sorted(self.extra.items()):
            w.node(uri, ("a", "fb:Country"), ("rdfs:label", lit(name, "en")))
