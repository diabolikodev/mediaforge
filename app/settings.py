import json
from pathlib import Path

from app.utils import ROOT_DIR


SETTINGS_PATH = ROOT_DIR / "mediaforge_settings.json"

DEFAULT_SETTINGS = {
    "default_mode": "audio_mp3",
    "default_audio_quality": "320k",
    "default_video_quality": "best",
    "embed_metadata": True,
    "embed_cover": True,
    "save_thumbnail": True,
    "save_description": False,
    "save_metadata_json": True,
    "expand_playlists": False,
    "playlist_limit": "50",
}

ALLOWED_MODES = {"audio_mp3", "audio_m4a", "audio_webm", "video_mp4", "best"}
ALLOWED_AUDIO_QUALITY = {"128k", "192k", "256k", "320k"}
ALLOWED_VIDEO_QUALITY = {"best", "1080p", "720p", "480p"}
ALLOWED_PLAYLIST_LIMITS = {"50", "100", "250", "unlimited"}
BOOLEAN_KEYS = {
    "embed_metadata",
    "embed_cover",
    "save_thumbnail",
    "save_description",
    "save_metadata_json",
    "expand_playlists",
}


def normalize_settings(data):
    settings = dict(DEFAULT_SETTINGS)

    if isinstance(data, dict):
        settings.update(data)

    if settings.get("default_mode") not in ALLOWED_MODES:
        settings["default_mode"] = DEFAULT_SETTINGS["default_mode"]

    if settings.get("default_audio_quality") not in ALLOWED_AUDIO_QUALITY:
        settings["default_audio_quality"] = DEFAULT_SETTINGS["default_audio_quality"]

    if settings.get("default_video_quality") not in ALLOWED_VIDEO_QUALITY:
        settings["default_video_quality"] = DEFAULT_SETTINGS["default_video_quality"]

    settings["playlist_limit"] = str(settings.get("playlist_limit") or DEFAULT_SETTINGS["playlist_limit"])

    if settings["playlist_limit"] not in ALLOWED_PLAYLIST_LIMITS:
        settings["playlist_limit"] = DEFAULT_SETTINGS["playlist_limit"]

    for key in BOOLEAN_KEYS:
        settings[key] = bool(settings.get(key))

    return settings


def load_settings():
    if not SETTINGS_PATH.exists():
        return dict(DEFAULT_SETTINGS)

    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_SETTINGS)

    return normalize_settings(data)


def save_settings(data):
    settings = normalize_settings(data)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return settings
