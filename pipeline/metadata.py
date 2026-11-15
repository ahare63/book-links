"""Original publication years from Wikidata."""

import json
import os
import sys
import urllib.parse

from pipeline.sources import http

WIKIDATA_URL = "https://query.wikidata.org/sparql"

QUERY = """\
SELECT ?pg (MIN(YEAR(?date)) AS ?year) WHERE {{
  VALUES ?pg {{ {ids} }}
  ?item wdt:P2034 ?pg ;
        wdt:P577 ?date .
}} GROUP BY ?pg"""


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("years", help="fill in missing publication years from Wikidata")
    parser.set_defaults(func=years)


def years(store, args):
    missing = {
        row["source_ref"]: row["id"]
        for row in store.conn.execute(
            "SELECT id, source_ref FROM works WHERE source = 'gutenberg-us' AND year IS NULL"
        )
    }
    if not missing:
        return 0
    query = QUERY.format(ids=" ".join(json.dumps(ref) for ref in missing))
    endpoint = os.environ.get("BOOK_LINKS_WIKIDATA_URL", WIKIDATA_URL)
    url = endpoint + "?" + urllib.parse.urlencode({"format": "json", "query": query})
    try:
        answer = json.loads(http.fetch(url))
    except (http.FetchError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for binding in answer["results"]["bindings"]:
        work_id = missing.get(binding["pg"]["value"])
        if work_id is not None:
            store.conn.execute(
                "UPDATE works SET year = ? WHERE id = ? AND year IS NULL",
                (int(binding["year"]["value"]), work_id),
            )
    return 0
