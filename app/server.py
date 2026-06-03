import json
import mimetypes
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.jobs import jobs, run_background
from app.media import analyze_url, download_job
from app.utils import DOWNLOAD_DIR, STATIC_DIR, ValidationError, validate_media_url


APP_NAME = "MediaForge"
APP_VERSION = "1.0.1"

HOST = "127.0.0.1"
PORT = 8787
MAX_ACTIVE_JOBS = 2
DEBUG = os.getenv("MEDIAFORGE_DEBUG", "0") == "1"
AUTO_OPEN = os.getenv("MEDIAFORGE_AUTO_OPEN", "1") != "0"


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))

    if length <= 0:
        return {}

    if length > 64 * 1024:
        raise ValueError("Request body too large.")

    body = handler.rfile.read(length)
    return json.loads(body.decode("utf-8"))


def safe_static_path(route: str) -> Path | None:
    relative = route.replace("/static/", "", 1).lstrip("/")
    candidate = (STATIC_DIR / relative).resolve()
    static_root = STATIC_DIR.resolve()

    try:
        candidate.relative_to(static_root)
    except ValueError:
        return None

    return candidate


def serve_file(handler, path):
    if not path or not path.exists() or not path.is_file():
        handler.send_error(404)
        return

    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    data = path.read_bytes()

    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(data)


def open_downloads_folder():
    if sys.platform.startswith("win"):
        os.startfile(DOWNLOAD_DIR)
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", str(DOWNLOAD_DIR)])
        return

    subprocess.Popen(["xdg-open", str(DOWNLOAD_DIR)])


class MediaForgeHandler(BaseHTTPRequestHandler):
    server_version = "MediaForge/1.0.1"

    def log_message(self, format, *args):
        if DEBUG:
            print("[mediaforge]", format % args)

    def do_GET(self):
        route = urlparse(self.path).path

        if route == "/":
            serve_file(self, STATIC_DIR / "index.html")
            return

        if route.startswith("/static/"):
            serve_file(self, safe_static_path(route))
            return

        if route == "/health":
            json_response(self, 200, {"ok": True,"app": APP_NAME,"version": APP_VERSION})
            return

        if route == "/api/jobs":
            json_response(self, 200, jobs.list())
            return

        if route.startswith("/api/jobs/"):
            job_id = route.rsplit("/", 1)[-1]
            job = jobs.get(job_id)
            if not job:
                json_response(self, 404, {"detail": "Job not found"})
                return
            json_response(self, 200, job)
            return

        self.send_error(404)

    def do_DELETE(self):
        route = urlparse(self.path).path

        if route == "/api/jobs/completed":
            result = jobs.clear_completed()
            json_response(self, 200, result)
            return

        if route == "/api/jobs":
            result = jobs.clear_all()
            status = 409 if result.get("blocked") else 200
            json_response(self, status, result)
            return

        self.send_error(404)

    def do_POST(self):
        route = urlparse(self.path).path

        try:
            payload = read_json(self)
        except Exception as exc:
            json_response(self, 400, {"detail": str(exc) or "Invalid JSON"})
            return

        if route == "/api/open-downloads":
            try:
                DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                open_downloads_folder()
                json_response(self, 200, {"ok": True, "path": str(DOWNLOAD_DIR)})
            except Exception as exc:
                json_response(self, 500, {"detail": str(exc)})
            return

        if route == "/api/analyze":
            try:
                url = validate_media_url(payload.get("url"))
                info = analyze_url(url)
                json_response(self, 200, info)
            except ValidationError as exc:
                json_response(self, 400, {"detail": str(exc)})
            except Exception as exc:
                json_response(self, 400, {"detail": str(exc)})
            return

        if route == "/api/download":
            try:
                validate_media_url(payload.get("url"))

                if jobs.active_count() >= MAX_ACTIVE_JOBS:
                    json_response(self, 429, {"detail": "Too many active jobs. Wait for one to finish."})
                    return

                job = jobs.create()
                jobs.update(
                    job["id"],
                    mode=payload.get("mode"),
                    quality=payload.get("quality"),
                    video_quality=payload.get("video_quality"),
                )
                run_background(download_job, job["id"], payload)
                json_response(self, 200, jobs.get(job["id"]))
            except ValidationError as exc:
                json_response(self, 400, {"detail": str(exc)})
            except Exception as exc:
                json_response(self, 400, {"detail": str(exc)})
            return

        self.send_error(404)


def open_browser():
    webbrowser.open(f"http://{HOST}:{PORT}")


def run_server():
    server = ThreadingHTTPServer((HOST, PORT), MediaForgeHandler)
    url = f"http://{HOST}:{PORT}"

    print(f"MediaForge running at {url}")
    print("Server is local-only.")
    print("Logs are hidden. Set MEDIAFORGE_DEBUG=1 to show request logs.")

    if AUTO_OPEN:
        threading.Timer(0.8, open_browser).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping MediaForge...")
    finally:
        server.server_close()
