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
from app.media import analyze_url, download_job, expand_playlist_urls, normalize_download_request
from app.settings import load_settings, save_settings
from app.utils import DOWNLOAD_DIR, STATIC_DIR, ValidationError, validate_media_url


APP_NAME = "MediaForge"
APP_VERSION = "1.1.0"

HOST = "127.0.0.1"
PORT = 8787
MAX_ACTIVE_JOBS = 2
MAX_INPUT_URLS = 50
DOWNLOAD_SLOTS = threading.BoundedSemaphore(MAX_ACTIVE_JOBS)
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

    if length > 128 * 1024:
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


def safe_download_path(path_value):
    if not path_value:
        raise ValueError("Missing path.")

    candidate = Path(path_value).resolve()
    download_root = DOWNLOAD_DIR.resolve()

    try:
        candidate.relative_to(download_root)
    except ValueError as exc:
        raise ValueError("Path is outside the downloads folder.") from exc

    if not candidate.exists():
        raise ValueError("Path does not exist.")

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


def open_folder(path):
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer", str(path)])
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return

    subprocess.Popen(["xdg-open", str(path)])


def playlist_limit_from_payload(payload):
    value = str(payload.get("playlist_limit") or "50").strip().lower()

    if value in {"unlimited", "none", "0"}:
        return None

    try:
        limit = int(value)
    except ValueError:
        limit = 50

    if limit not in {50, 100, 250}:
        limit = 50

    return limit


def split_urls(payload):
    urls = payload.get("urls")

    if isinstance(urls, str):
        urls = urls.replace(",", "\n").splitlines()

    if not isinstance(urls, list):
        url = payload.get("url")
        urls = [url] if url else []

    cleaned = []
    seen = set()

    for item in urls:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        cleaned.append(value)
        seen.add(value)

    if not cleaned:
        raise ValidationError("Missing URL.")

    if len(cleaned) > MAX_INPUT_URLS:
        raise ValidationError(f"Input limit is {MAX_INPUT_URLS} URLs.")

    return cleaned


def run_download_slot(job_id, request):
    if not jobs.wait_for_queue(job_id):
        return

    with DOWNLOAD_SLOTS:
        if not jobs.wait_for_queue(job_id):
            return

        download_job(job_id, request)


def collect_media_urls(payload):
    source_urls = split_urls(payload)
    expand_playlists = bool(payload.get("expand_playlists"))
    playlist_limit = playlist_limit_from_payload(payload)
    collected = []
    seen = set()
    playlists = 0
    truncated = False

    for source_url in source_urls:
        validated = validate_media_url(source_url)
        candidates = [validated]

        if expand_playlists:
            remaining = None if playlist_limit is None else playlist_limit - len(collected)

            if remaining is not None and remaining <= 0:
                truncated = True
                break

            expanded = expand_playlist_urls(validated, remaining)
            candidates = expanded.get("urls") or [validated]

            if expanded.get("is_playlist"):
                playlists += 1

            if expanded.get("truncated"):
                truncated = True

        for candidate in candidates:
            if playlist_limit is not None and len(collected) >= playlist_limit:
                truncated = True
                break

            value = validate_media_url(candidate)

            if value in seen:
                continue

            collected.append(value)
            seen.add(value)

    if not collected:
        raise ValidationError("Missing URL.")

    return collected, {
        "input_count": len(source_urls),
        "count": len(collected),
        "expanded_playlists": playlists,
        "playlist_expansion": expand_playlists,
        "limit": playlist_limit,
        "limit_label": "unlimited" if playlist_limit is None else str(playlist_limit),
        "truncated": truncated,
    }


def create_download_jobs(payload):
    urls, batch = collect_media_urls(payload)
    active = jobs.active_count()

    if active >= MAX_ACTIVE_JOBS:
        raise RuntimeError("Too many active jobs. Wait for one to finish.")

    created = []

    for url in urls:
        request = dict(payload)
        request.pop("urls", None)
        request["url"] = validate_media_url(url)
        request["expand_playlists"] = False
        request = normalize_download_request(request)
        job = jobs.create(request)
        run_background(run_download_slot, job["id"], request)
        created.append(jobs.get(job["id"]))

    return created, batch


class MediaForgeHandler(BaseHTTPRequestHandler):
    server_version = "MediaForge/1.1.0"

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
            json_response(self, 200, {"ok": True, "app": APP_NAME, "version": APP_VERSION})
            return

        if route == "/api/settings":
            json_response(self, 200, load_settings())
            return

        if route == "/api/queue":
            json_response(self, 200, jobs.queue_status())
            return

        if route == "/api/jobs":
            json_response(self, 200, jobs.list())
            return

        if route.startswith("/api/jobs/"):
            job_id = route.strip("/").split("/")[-1]
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

        if route == "/api/jobs/visible":
            query = urlparse(self.path).query
            params = dict(part.split("=", 1) for part in query.split("&") if "=" in part)
            result = jobs.clear_by_filter(params.get("status"))
            status = 409 if result.get("blocked") else 200
            json_response(self, status, result)
            return

        if route.startswith("/api/jobs/"):
            job_id = route.strip("/").split("/")[-1]
            result = jobs.remove(job_id)
            if result.get("detail") == "Job not found.":
                json_response(self, 404, result)
                return
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

        if route == "/api/settings":
            try:
                settings = save_settings(payload)
                json_response(self, 200, settings)
            except Exception as exc:
                json_response(self, 400, {"detail": str(exc)})
            return

        if route == "/api/queue/pause":
            json_response(self, 200, jobs.pause_queue())
            return

        if route == "/api/queue/resume":
            json_response(self, 200, jobs.resume_queue())
            return

        if route == "/api/queue/cancel-queued":
            json_response(self, 200, jobs.cancel_queued())
            return

        if route == "/api/queue/cancel-active":
            json_response(self, 200, jobs.cancel_active())
            return

        if route == "/api/open-downloads":
            try:
                DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                open_folder(DOWNLOAD_DIR)
                json_response(self, 200, {"ok": True, "path": str(DOWNLOAD_DIR)})
            except Exception as exc:
                json_response(self, 500, {"detail": str(exc)})
            return

        if route.endswith("/open-output") and route.startswith("/api/jobs/"):
            try:
                job_id = route.strip("/").split("/")[-2]
                job = jobs.get(job_id)

                if not job:
                    json_response(self, 404, {"detail": "Job not found"})
                    return

                path = safe_download_path(job.get("output_dir"))
                open_folder(path)
                json_response(self, 200, {"ok": True, "path": str(path)})
            except Exception as exc:
                json_response(self, 400, {"detail": str(exc)})
            return

        if route.endswith("/cancel") and route.startswith("/api/jobs/"):
            job_id = route.strip("/").split("/")[-2]
            result = jobs.cancel(job_id)

            if result.get("detail") == "Job not found.":
                json_response(self, 404, result)
                return

            status = 409 if result.get("cancelled") == 0 else 200
            json_response(self, status, result)
            return

        if route.endswith("/retry") and route.startswith("/api/jobs/"):
            try:
                job_id = route.strip("/").split("/")[-2]
                job = jobs.get(job_id)

                if not job:
                    json_response(self, 404, {"detail": "Job not found"})
                    return

                if job.get("status") != "failed":
                    json_response(self, 409, {"detail": "Only failed jobs can be retried."})
                    return

                if jobs.active_count() >= MAX_ACTIVE_JOBS:
                    json_response(self, 429, {"detail": "Too many active jobs. Wait for one to finish."})
                    return

                request = normalize_download_request(job.get("request") or {"url": job.get("url")})
                new_job = jobs.create(request)
                run_background(run_download_slot, new_job["id"], request)
                json_response(self, 200, jobs.get(new_job["id"]))
            except Exception as exc:
                json_response(self, 400, {"detail": str(exc)})
            return

        if route == "/api/analyze":
            try:
                urls, batch = collect_media_urls(payload)
                info = analyze_url(urls[0])
                info["batch"] = batch
                json_response(self, 200, info)
            except ValidationError as exc:
                json_response(self, 400, {"detail": str(exc)})
            except Exception as exc:
                json_response(self, 400, {"detail": str(exc)})
            return

        if route == "/api/download":
            try:
                created, batch = create_download_jobs(payload)
                payload_out = {
                    "jobs": created,
                    "count": len(created),
                    "id": created[0]["id"] if len(created) == 1 else None,
                    "batch": batch,
                }
                json_response(self, 200, payload_out)
            except ValidationError as exc:
                json_response(self, 400, {"detail": str(exc)})
            except RuntimeError as exc:
                json_response(self, 429, {"detail": str(exc)})
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
