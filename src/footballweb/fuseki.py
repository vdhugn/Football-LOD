"""Thin read-only client for the Fuseki SPARQL query endpoint."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request


class FusekiError(Exception):
    """The endpoint rejected the query (HTTP 4xx)."""


class FusekiUnavailable(Exception):
    """The endpoint could not be reached (network error)."""


class FusekiFailure(FusekiUnavailable):
    """The endpoint answered with a server error (HTTP 5xx); the message is Fuseki's own."""


MAX_BYTES = 20 * 1024 * 1024


class FusekiClient:
    def __init__(self, base_url, timeout=60, max_bytes=MAX_BYTES):
        self.endpoint = base_url.rstrip("/") + "/sparql"
        self.timeout = timeout
        self.max_bytes = max_bytes

    def _slow(self):
        return FusekiError(f"The query took longer than {self.timeout} seconds.")

    def _post(self, query, accept):
        # "timeout" asks Fuseki itself to stop the query; the deadline below bounds the whole exchange
        data = urllib.parse.urlencode({"query": query, "timeout": str(int(self.timeout * 1000))}).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=data, headers={
            "Accept": accept, "Content-Type": "application/x-www-form-urlencoded"})
        deadline = time.monotonic() + self.timeout
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                chunks, size = [], 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise FusekiError(f"The result is larger than {self.max_bytes // (1024 * 1024)} MB; add a LIMIT.")
                    if time.monotonic() > deadline:
                        raise self._slow()
                    chunks.append(chunk)
                return b"".join(chunks).decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace").strip()[:500] or f"HTTP {e.code}"
            raise (FusekiError if e.code < 500 else FusekiFailure)(body) from e
        except TimeoutError as e:
            raise self._slow() from e
        except (urllib.error.URLError, OSError) as e:
            raise FusekiUnavailable(str(e)) from e

    def select(self, query):
        return json.loads(self._post(query, "application/sparql-results+json"))

    def ask(self, query):
        return bool(json.loads(self._post(query, "application/sparql-results+json"))["boolean"])

    def construct(self, query):
        return self._post(query, "text/turtle")
