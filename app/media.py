import json
import shutil
from datetime import datetime

import requests
import yt_dlp

from app.jobs import jobs
from app.utils import DOWNLOAD_DIR, duration_string, slugify, validate_media_url


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


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def download_thumbnail(url, out_path):
    if not url:
        return False

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()

        if "image" not in content_type and len(response.content) > 0:
            # Some CDNs do not return a perfect content-type, so we avoid failing hard.
            pass

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


def download_job(job_id, request):
    url = request.get("url")

    try:
        url = validate_media_url(url)
        mode = request.get("mode", "audio_mp3")
        quality = request.get("quality", "320k")
        video_quality = request.get("video_quality", "best")

        allowed_modes = {"audio_mp3", "audio_m4a", "audio_webm", "video_mp4", "best"}
        allowed_audio_quality = {"128k", "192k", "256k", "320k"}
        allowed_video_quality = {"best", "1080p", "720p", "480p"}

        if mode not in allowed_modes:
            raise ValueError("Invalid download mode.")

        if quality not in allowed_audio_quality:
            raise ValueError("Invalid audio quality.")

        if video_quality not in allowed_video_quality:
            raise ValueError("Invalid video quality.")

        if mode in {"audio_mp3", "audio_m4a", "video_mp4"} and not ffmpeg_available():
            jobs.update(
                job_id,
                status="failed",
                progress=0,
                message="ffmpeg missing",
                error="FFmpeg is required for this mode but was not found in PATH.",
                mode=mode,
                quality=quality,
                video_quality=video_quality,
            )
            return

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

        output_template = str(output_dir / "%(title).120s.%(ext)s")
        options = build_ydl_options(request, output_template, progress_hook)

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

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
        jobs.update(
            job_id,
            status="failed",
            progress=0,
            message="failed",
            error=str(exc),
        )
