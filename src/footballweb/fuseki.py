"""Thin read-only client for the Fuseki SPARQL query endpoint."""
import json
import urllib.error
import urllib.parse
import urllib.request


class FusekiError(Exception):
    """The endpoint rejected the query (HTTP 4xx)."""


class FusekiUnavailable(Exception):
    """The endpoint could not be reached or failed (network error, HTTP 5xx)."""


class FusekiClient:
    def __init__(self, base_url, timeout=60):
        self.endpoint = base_url.rstrip("/") + "/sparql"
        self.timeout = timeout

    def _post(self, query, accept):
        data = urllib.parse.urlencode({"query": query}).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=data, headers={
            "Accept": accept, "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace").strip()[:500] or f"HTTP {e.code}"
            raise (FusekiError if e.code < 500 else FusekiUnavailable)(body) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise FusekiUnavailable(str(e)) from e

    def select(self, query):
        return json.loads(self._post(query, "application/sparql-results+json"))

    def ask(self, query):
        return bool(json.loads(self._post(query, "application/sparql-results+json"))["boolean"])

    def construct(self, query):
        return self._post(query, "text/turtle")
