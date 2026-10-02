"""SPARQL helpers: literal escaping and a read-only query guard."""
import re

_ESC = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}

# strings, IRIs and comments, matched left to right so that '#' inside a string or IRI
# and quotes inside a comment never confuse each other
_NOISE = re.compile(
    r'"""(?s:.*?)"""|\'\'\'(?s:.*?)\'\'\'|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\''
    r"|<[^<>\"{}|^`\\\s]*>|#[^\n]*"
)
_WORD = re.compile(r"(?<![?$:@.\w-])[A-Za-z_]+(?![\w:.-])")
UPDATE_WORDS = {"INSERT", "DELETE", "LOAD", "CLEAR", "DROP", "CREATE", "COPY", "MOVE", "ADD", "WITH"}
FORMS = ("SELECT", "ASK", "CONSTRUCT", "DESCRIBE")


def escape_literal(text):
    """Escape text for use inside a double-quoted SPARQL string literal."""
    return "".join(_ESC.get(c, c) for c in text)


def query_form(query):
    """Return 'select', 'ask', 'construct' or 'describe'; raise ValueError for anything else."""
    cleaned = _NOISE.sub(" ", query)
    words = [w.upper() for w in _WORD.findall(cleaned)]
    if any(w in UPDATE_WORDS for w in words):
        raise ValueError("Update operations are not allowed; use SELECT, ASK, CONSTRUCT or DESCRIBE.")
    for w in words:
        if w in FORMS:
            return w.lower()
    raise ValueError("Only SELECT, ASK, CONSTRUCT and DESCRIBE queries are allowed.")
