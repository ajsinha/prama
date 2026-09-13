"""A flexible local HTTP test server for the REST connector cases."""
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

STATE = {}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, headers=None, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if isinstance(body, (dict, list)):
            self.wfile.write(json.dumps(body).encode())
        else:
            self.wfile.write(body.encode() if isinstance(body, str) else body)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path

        auth = self.headers.get(STATE.get("auth_header_name", "Authorization"))
        STATE.setdefault("received_auth_headers", []).append(auth)
        STATE.setdefault("received_paths", []).append(self.path)

        if path == "/paginate":
            page = int(query.get("page", ["1"])[0])
            total_pages = STATE.get("total_pages", 400)
            page_size = STATE.get("page_size", 100)
            start = (page - 1) * page_size
            records = [{"id": start + i} for i in range(page_size)]
            body = {"items": records}
            if page < total_pages:
                body["links"] = {"next": f"http://127.0.0.1:{STATE['port']}/paginate?page={page+1}"}
            self._send(200, body)
            return

        if path == "/cycle":
            page = int(query.get("page", ["1"])[0])
            records = [{"id": page * 100 + i} for i in range(10)]
            body = {"items": records}
            if page < 3:
                body["links"] = {"next": f"http://127.0.0.1:{STATE['port']}/cycle?page={page+1}"}
            else:
                # page 3 links back to the EXACT URL first requested (bare, no ?page=1)
                body["links"] = {"next": f"http://127.0.0.1:{STATE['port']}/cycle"}
            self._send(200, body)
            return

        if path == "/manypages":
            page = int(query.get("page", ["1"])[0])
            total = STATE.get("total_pages", 50)
            records = [{"id": page * 10 + i} for i in range(10)]
            body = {"items": records}
            if page < total:
                body["links"] = {"next": f"http://127.0.0.1:{STATE['port']}/manypages?page={page+1}"}
            self._send(200, body)
            return

        if path == "/pageparam":
            page = int(query.get("p", ["1"])[0])
            STATE.setdefault("pageparam_urls", []).append(self.path)
            records = [{"id": page * 5 + i} for i in range(5)]
            body = {"items": records}
            if page < STATE.get("total_pages", 5):
                body["links"] = {"next": f"http://127.0.0.1:{STATE['port']}/pageparam?p={page+1}"}
            self._send(200, body)
            return

        if path == "/ratelimit":
            seq = STATE.setdefault("_ratelimit_calls", [])
            idx = len(seq)
            seq.append(True)
            plan = STATE.get("retry_after_sequence", [])
            if idx < len(plan):
                ra = plan[idx]
                headers = {}
                if ra is not None:
                    headers["Retry-After"] = str(ra)
                self._send(429, {}, headers=headers)
                return
            self._send(200, {"items": [{"id": 1}]})
            return

        if path == "/ratelimit_forever":
            self._send(429, {}, headers={"Retry-After": "0"})
            return

        if path == "/status":
            code = int(query.get("code", ["200"])[0])
            self._send(code, {"msg": "response"})
            return

        if path == "/mixedtypes":
            records = []
            for i in range(200):
                rec = {"id": i, "amount": "STRINGVAL" if i == 50 else float(i)}
                if i >= 150:
                    pass  # settled_at absent for 50 of them (i in [150,200))
                else:
                    rec["settled_at"] = "2026-04-01"
                records.append(rec)
            self._send(200, {"items": records})
            return

        if path == "/nested":
            records = [
                {"id": 1, "legs": [{"side": "buy", "qty": 1}, {"side": "sell", "qty": 2}]},
                {"id": 2, "legs": [{"qty": 1, "side": "buy"}, {"qty": 2, "side": "sell"}]},
            ]
            self._send(200, {"items": records})
            return

        if path == "/notjson":
            self._send(200, "<html><body>not json</body></html>", content_type="text/html")
            return

        if path == "/bigpages":
            page = int(query.get("page", ["1"])[0])
            total = STATE.get("total_pages", 1000)
            records = [{"id": page * 1000 + i, "pad": "x" * 50} for i in range(1000)]
            body = {"items": records}
            if page < total:
                body["links"] = {"next": f"http://127.0.0.1:{STATE['port']}/bigpages?page={page+1}"}
            self._send(200, body)
            return

        if path == "":
            self._send(200, {"items": []})
            return

        self._send(200, {"items": []})


def start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    STATE["port"] = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, STATE["port"]
