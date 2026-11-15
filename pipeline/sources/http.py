"""Polite single-file HTTP fetching."""

import os
import time
import urllib.error
import urllib.request

USER_AGENT = "book-links/0.1"
TIMEOUT_SECONDS = 60


class FetchError(Exception):
    """A request failed; the message is a one-line reason."""


def fetch(url):
    """GET one URL after the configured delay and return the body bytes."""
    time.sleep(float(os.environ.get("BOOK_LINKS_FETCH_DELAY", "2")))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise FetchError(f"{url}: HTTP {error.code} {error.reason}") from None
    except (urllib.error.URLError, OSError) as error:
        raise FetchError(f"{url}: {getattr(error, 'reason', error)}") from None
