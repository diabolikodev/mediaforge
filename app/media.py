import json
import re
import shutil
from datetime import datetime

import requests
import yt_dlp

from app.jobs import jobs
from app.settings import ALLOWED_AUDIO_QUALITY, ALLOWED_MODES, ALLOWED_VIDEO_QUALITY
from app.utils import DOWNLOAD_DIR, duration_string, slugify, validate_media_url


class CancelledDownload(Exception):
    pass


def ensure_not_cancelled(job_id):
    if jobs.is_cancelled(job_id):
        raise CancelledDownload("Cancelled by user.")


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def analyze_url(url):
    url = validate_media_url(url)

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = info.get("formats") or []

    return {
        "id": info.get("id"),
        "title": info.get("title") or "Untitled",
        "uploader": info.get("uploader"),
        "channel": info.get("channel"),
        "duration": info.get("duration"),
        "duration_string": duration_string(info.get("duration")),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or url,
        "description": info.get("description"),
        "formats_count": len(formats),
        "raw": {
            "extractor": info.get("extractor"),
            "ext": info.get("ext"),
            "tags": info.get("tags"),
            "categories": info.get("categories"),
            "upload_date": info.get("upload_date"),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
        },
    }


def playlist_entry_url(entry):
    for key in ["webpage_url", "original_url", "url"]:
        value = entry.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value

    video_id = entry.get("id")

    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"

    return None


def expand_playlist_urls(url, limit=50):
    url = validate_media_url(url)

    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
        "ignoreerrors": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = info.get("entries") or []

    if not entries:
        return {
            "urls": [url],
            "is_playlist": False,
            "title": info.get("title"),
            "entry_count": 1,
            "truncated": False,
        }

    urls = []
    seen = set()

    for entry in entries:
        if not entry:
            continue

        value = playlist_entry_url(entry)

        if not value or value in seen:
            continue

        urls.append(value)
        seen.add(value)

        if limit is not None and len(urls) >= limit:
            break

    return {
        "urls": urls or [url],
        "is_playlist": True,
        "title": info.get("title"),
        "entry_count": len(entries),
        "truncated": limit is not None and len(entries) > len(urls),
    }


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def download_thumbnail(url, out_path):
    if not url:
        return False

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        out_path.write_bytes(response.content)
        return True
    except Exception:
        return False


def build_video_format(video_quality: str) -> str:
    if video_quality == "1080p":
        return "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]/best"
    if video_quality == "720p":
        return "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best"
    if video_quality == "480p":
        return "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]/best"
    return "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best"


def classify_error(exc):
    if isinstance(exc, CancelledDownload):
        return "Cancelled.", "cancelled", "Cancelled by user."

    detail = str(exc) or "Unexpected error."
    detail = re.sub(r"\x1b\[[0-9;]*m", "", detail).strip()
    lowered = detail.lower()

    if "403" in lowered or "forbidden" in lowered:
        return "Access forbidden by the platform.", "forbidden", detail

    if "ffmpeg" in lowered:
        return "FFmpeg not found or failed.", "ffmpeg", detail

    if "unsupported url" in lowered or "not a valid url" in lowered:
        return "Unsupported URL.", "unsupported_url", detail

    if "private" in lowered or "login" in lowered or "sign in" in lowered or "cookies" in lowered:
        return "Login or cookies may be required.", "login_required", detail

    if "unavailable" in lowered or "removed" in lowered or "copyright" in lowered:
        return "Media unavailable.", "unavailable", detail

    if "timed out" in lowered or "timeout" in lowered or "network" in lowered or "connection" in lowered:
        return "Network error.", "network", detail

    if "requested format is not available" in lowered or "format is not available" in lowered:
        return "Requested format is not available.", "format_unavailable", detail

    return "Download failed.", "download_failed", detail


def build_ydl_options(request, output_template, progress_hook):
    mode = request.get("mode", "audio_mp3")
    quality = request.get("quality", "320k")
    video_quality = request.get("video_quality", "best")

    options = {
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [progress_hook],
        "restrictfilenames": False,
        "windowsfilenames": True,
        "writethumbnail": bool(request.get("save_thumbnail") or request.get("embed_cover")),
        "writedescription": bool(request.get("save_description")),
        "writeinfojson": bool(request.get("save_metadata_json")),
        "embedmetadata": bool(request.get("embed_metadata")),
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
    }

    if mode == "audio_mp3":
        options.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": str(quality).replace("k", ""),
                    },
                    {"key": "FFmpegMetadata"},
                ],
            }
        )
        if request.get("embed_cover"):
            options["postprocessors"].append({"key": "EmbedThumbnail"})

    elif mode == "audio_m4a":
        options.update(
            {
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
                    {"key": "FFmpegMetadata"},
                ],
            }
        )

    elif mode == "audio_webm":
        options.update({"format": "bestaudio[ext=webm]/bestaudio/best"})

    elif mode == "video_mp4":
        options.update(
            {
                "format": build_video_format(video_quality),
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegMetadata"}] if request.get("embed_metadata") else [],
            }
        )

    else:
        options.update({"format": "best"})

    return options


def normalize_download_request(request):
    normalized = dict(request or {})
    normalized["url"] = validate_media_url(normalized.get("url"))
    normalized["mode"] = normalized.get("mode") or "audio_mp3"
    normalized["quality"] = normalized.get("quality") or "320k"
    normalized["video_quality"] = normalized.get("video_quality") or "best"

    if normalized["mode"] not in ALLOWED_MODES:
        raise ValueError("Invalid download mode.")

    if normalized["quality"] not in ALLOWED_AUDIO_QUALITY:
        raise ValueError("Invalid audio quality.")

    if normalized["video_quality"] not in ALLOWED_VIDEO_QUALITY:
        raise ValueError("Invalid video quality.")

    for key in ["embed_metadata", "embed_cover", "save_thumbnail", "save_description", "save_metadata_json"]:
        normalized[key] = bool(normalized.get(key))

    return normalized


def download_job(job_id, request):
    try:
        ensure_not_cancelled(job_id)
        request = normalize_download_request(request)
        url = request["url"]
        mode = request["mode"]
        quality = request["quality"]
        video_quality = request["video_quality"]

        jobs.update(
            job_id,
            url=url,
            request=request,
            mode=mode,
            quality=quality,
            video_quality=video_quality,
        )

        ensure_not_cancelled(job_id)

        if mode in {"audio_mp3", "audio_m4a", "video_mp4"} and not ffmpeg_available():
            jobs.update(
                job_id,
                status="failed",
                progress=0,
                message="FFmpeg not found or failed.",
                error="FFmpeg not found or failed.",
                error_code="ffmpeg",
                error_detail="FFmpeg is required for this mode but was not found in PATH.",
                mode=mode,
                quality=quality,
                video_quality=video_quality,
            )
            return

        ensure_not_cancelled(job_id)

        jobs.update(
            job_id,
            status="analyzing",
            progress=2,
            message="analyzing url",
            mode=mode,
            quality=quality,
            video_quality=video_quality,
        )
        info = analyze_url(url)
        ensure_not_cancelled(job_id)

        title_slug = slugify(info.get("title") or "untitled")
        mode_slug = slugify(mode)
        date_slug = datetime.now().strftime("%Y-%m-%d")

        base_dir = DOWNLOAD_DIR / date_slug / mode_slug
        output_dir = base_dir / title_slug

        if output_dir.exists():
            suffix = 2
            while (base_dir / f"{title_slug}_{suffix}").exists():
                suffix += 1
            output_dir = base_dir / f"{title_slug}_{suffix}"

        output_dir.mkdir(parents=True, exist_ok=True)
        ensure_not_cancelled(job_id)

        jobs.update(
            job_id,
            title=info.get("title"),
            output_dir=str(output_dir),
            status="downloading",
            progress=5,
            message="starting download",
        )

        if request.get("save_metadata_json", True):
            write_json(output_dir / "mediaforge_metadata.json", info)

        if request.get("save_description") and info.get("description"):
            (output_dir / "description.txt").write_text(info["description"], encoding="utf-8")

        if request.get("save_thumbnail", True):
            download_thumbnail(info.get("thumbnail"), output_dir / "cover.jpg")

        def progress_hook(data):
            ensure_not_cancelled(job_id)
            status = data.get("status")

            if status == "downloading":
                downloaded = data.get("downloaded_bytes") or 0
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                percent = 0

                if total:
                    percent = min(85, max(5, downloaded / total * 80))

                jobs.update(
                    job_id,
                    status="downloading",
                    progress=round(percent, 2),
                    message=(data.get("_percent_str") or "downloading").strip(),
                )

            elif status == "finished":
                jobs.update(job_id, status="converting", progress=88, message="processing file")

        ensure_not_cancelled(job_id)
        output_template = str(output_dir / "%(title).120s.%(ext)s")
        options = build_ydl_options(request, output_template, progress_hook)

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        ensure_not_cancelled(job_id)

        output_files = [
            str(path.relative_to(DOWNLOAD_DIR))
            for path in output_dir.glob("*")
            if path.is_file()
        ]

        jobs.update(
            job_id,
            status="completed",
            progress=100,
            message="completed",
            output_files=output_files,
        )

    except Exception as exc:
        message, code, detail = classify_error(exc)
        status = "cancelled" if code == "cancelled" else "failed"
        jobs.update(
            job_id,
            status=status,
            progress=0,
            message=message,
            error=None if code == "cancelled" else message,
            error_code=code,
            error_detail=None if code == "cancelled" else detail,
            cancel_requested=code == "cancelled",
        )
