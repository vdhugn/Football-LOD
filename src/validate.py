"""Vocabulary check: every fb: term used in generated Turtle must exist in the ontology.

CLI: python src/validate.py vocab
"""
import re
import sys
from pathlib import Path

from rdflib import Graph

_USED = re.compile(r"\bfb:([A-Za-z][A-Za-z0-9]*)")


def ontology_terms(path, onto_base):
    g = Graph()
    g.parse(str(path), format="turtle")
    return {str(s)[len(onto_base):] for s in set(g.subjects())
            if str(s).startswith(onto_base)}


def used_terms(files):
    terms = set()
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                terms.update(_USED.findall(line))
    return terms


def check_vocabulary(ontology_path, files, onto_base):
    return used_terms(files) - ontology_terms(ontology_path, onto_base)


def main(argv=None):
    from common import load_config
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["vocab"]:
        print("usage: validate.py vocab")
        return 2
    cfg = load_config()
    files = sorted((Path(cfg["out_dir"]) / "data").glob("*.ttl"))
    missing = check_vocabulary("ontology/football.ttl", files, cfg["ontology_base"])
    if missing:
        print("Undefined fb: terms:", ", ".join(sorted(missing)))
        return 1
    print(f"vocabulary OK ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
