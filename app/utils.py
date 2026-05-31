import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parents[1]
DOWNLOAD_DIR = ROOT_DIR / "downloads"
STATIC_DIR = ROOT_DIR / "app" / "static"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


class ValidationError(ValueError):
    pass


def slugify(value: str, fallback: str = "media") -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:80] or fallback


def duration_string(seconds):
    if seconds is None:
        return None

    try:
        seconds = int(seconds)
    except Exception:
        return None

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes}:{secs:02d}"


def validate_media_url(url: str) -> str:
    url = (url or "").strip()

    if not url:
        raise ValidationError("Missing URL.")

    if len(url) > 2048:
        raise ValidationError("URL is too long.")

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("Only http and https URLs are supported.")

    if not parsed.netloc:
        raise ValidationError("Invalid URL.")

    return url
