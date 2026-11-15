"""A local server: the built viewer, the graph, and endpoints for reviews and word lookups."""

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs

from pipeline.detectors.base import LINK_TYPES
from pipeline.export import build_graph
from pipeline.reviews import record_review
from pipeline.store import Store

DIST = Path(__file__).resolve().parent.parent / "viewer" / "dist"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json", ".svg": "image/svg+xml",
    ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".map": "application/json",
}


def term_counts(store, word):
    pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
    rows = store.conn.execute(
        "SELECT p.work_id, p.text FROM passages p JOIN works w ON w.id = p.work_id WHERE w.kind != 'subwork'"
    )
    counts = {}
    for row in rows:
        n = len(pattern.findall(row["text"]))
        if n:
            counts[row["work_id"]] = counts.get(row["work_id"], 0) + n
    return [{"id": work_id, "count": n} for work_id, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


MAX_BODY = 64 * 1024


def make_handler(data_dir):
    class Handler(BaseHTTPRequestHandler):
        def addressed_to_us(self):
            """False for requests a web page could make through DNS rebinding (wrong Host)."""
            port = self.server.server_port
            if self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}"):
                return True
            self.send(403, {"error": "unexpected Host header"})
            return False

        def send(self, status, body, content_type="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.addressed_to_us():
                return
            url = urlparse(self.path)
            if url.path == "/graph.json":
                with Store(data_dir) as store:
                    self.send(200, {**build_graph(store), "reviewable": True})
            elif url.path == "/api/term":
                word = parse_qs(url.query).get("q", [""])[0].strip()
                if not word:
                    return self.send(400, {"error": "missing q"})
                with Store(data_dir) as store:
                    self.send(200, {"term": word, "works": term_counts(store, word)})
            else:
                self.serve_static(unquote(url.path))

        def serve_static(self, path):
            if not DIST.is_dir():
                return self.send(404, "viewer not built: run `npm run build` in viewer/\n", "text/plain; charset=utf-8")
            try:
                target = (DIST / path.lstrip("/")).resolve()
            except (ValueError, OSError):
                return self.send(404, "not found\n", "text/plain; charset=utf-8")
            if path.endswith("/"):
                target = target / "index.html"
            if DIST not in target.parents and target != DIST or not target.is_file():
                return self.send(404, "not found\n", "text/plain; charset=utf-8")
            self.send(200, target.read_bytes(), CONTENT_TYPES.get(target.suffix, "application/octet-stream"))

        def do_POST(self):
            if not self.addressed_to_us():
                return
            if urlparse(self.path).path != "/api/review":
                return self.send(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                return self.send(400, {"error": "missing, bad or oversized Content-Length"})
            # A cross-site form or fetch cannot send this content type without a preflight we never answer.
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self.send(403, {"error": "reviews must be sent as application/json"})
            try:
                body = json.loads(self.rfile.read(length))
                link_id, verdict = body["link_id"], body["verdict"]
                corrected, note = body.get("type"), body.get("note")
                valid = (
                    isinstance(link_id, int) and not isinstance(link_id, bool)
                    and verdict in ("accept", "reject")
                    and (corrected is None or corrected in LINK_TYPES)
                    and (note is None or isinstance(note, str))
                )
            except (ValueError, KeyError, TypeError):
                valid = False
            if not valid:
                return self.send(400, {"error": "expected {link_id, verdict: accept|reject, type?, note?}"})
            with Store(data_dir) as store:
                found = record_review(store, link_id, verdict, corrected, note)
            if found:
                self.send(200, {"ok": True})
            else:
                self.send(404, {"error": f"no link with id {link_id}"})

        def log_message(self, format, *args):
            pass

    return Handler


def make_server(data_dir, port) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(data_dir))


def serve(store, args):
    httpd = make_server(store.data_dir, args.port)
    print(f"serving on http://127.0.0.1:{httpd.server_port}/ (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def register(commands):
    """Add this module's commands to the ``book-links`` command line."""
    parser = commands.add_parser("serve", help="serve the viewer and accept reviews on localhost")
    parser.add_argument("--port", type=int, default=8765)
    parser.set_defaults(func=serve)
