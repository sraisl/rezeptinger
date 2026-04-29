from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from html import unescape
from urllib.error import HTTPError

from yt_dlp import YoutubeDL

from .app_settings import language_preferences


class TranscriptUnavailable(Exception):
    pass


class YouTubeRateLimited(Exception):
    pass


@dataclass(frozen=True)
class YouTubeVideo:
    url: str
    video_id: str
    title: str
    channel: str
    thumbnail_url: str
    transcript: str


def fetch_video(url: str) -> YouTubeVideo:
    options = _youtube_options(
        {
            "extract_flat": False,
        }
    )

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise _youtube_error(exc) from exc

    transcript = _extract_transcript(info)
    if not transcript:
        raise TranscriptUnavailable(
            "Für dieses Video wurden keine nutzbaren Untertitel oder Auto-Untertitel gefunden."
        )

    return YouTubeVideo(
        url=url,
        video_id=info.get("id", ""),
        title=info.get("title", "") or "Unbenanntes Video",
        channel=info.get("channel") or info.get("uploader") or "",
        thumbnail_url=info.get("thumbnail") or "",
        transcript=transcript,
    )


def _youtube_options(extra: dict | None = None) -> dict:
    options = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "noplaylist": True,
    }
    cookies_file = os.environ.get("YT_DLP_COOKIES_FILE", "").strip()
    if cookies_file:
        options["cookiefile"] = cookies_file
    if extra:
        options.update(extra)
    return options


def _youtube_error(exc: Exception) -> Exception:
    if _is_rate_limit(exc):
        return YouTubeRateLimited(
            "Der YouTube-Abruf wurde mit HTTP 429 (Too Many Requests) abgelehnt. "
            "Warte etwas und versuche es erneut. Falls das häufiger passiert, nutze eine "
            "yt-dlp-Cookie-Datei über YT_DLP_COOKIES_FILE."
        )
    return TranscriptUnavailable(f"YouTube konnte nicht gelesen werden: {exc}")


def _is_rate_limit(exc: Exception) -> bool:
    if isinstance(exc, HTTPError) and exc.code == 429:
        return True
    message = str(exc).lower()
    return "429" in message or "too many requests" in message


def _extract_transcript(info: dict) -> str:
    subtitles = info.get("subtitles") or {}
    auto_captions = info.get("automatic_captions") or {}
    rate_limited = False

    for collection in (subtitles, auto_captions):
        for language in _preferred_languages(collection):
            text, track_rate_limited = _transcript_from_tracks(collection.get(language) or [])
            rate_limited = rate_limited or track_rate_limited
            if text:
                return text

    if rate_limited:
        raise YouTubeRateLimited(
            "Der YouTube-Untertitel-Endpunkt /api/timedtext wurde mit HTTP 429 "
            "(Too Many Requests) abgelehnt. Metadaten konnten gelesen werden, aber das "
            "Transkript nicht. Warte etwas und versuche es erneut oder nutze "
            "YT_DLP_COOKIES_FILE."
        )

    return ""


def _preferred_languages(collection: dict) -> list[str]:
    configured_languages = language_preferences()
    preferred = [*configured_languages, "de", "de-DE", "en", "en-US", "en-GB"]
    available = list(collection.keys())
    ordered = [language for language in preferred if language in collection]
    ordered.extend(language for language in available if language not in ordered)
    return list(dict.fromkeys(ordered))


def _transcript_from_tracks(tracks: list[dict]) -> tuple[str, bool]:
    rate_limited = False
    for extension in ("json3", "vtt", "srv3", "ttml"):
        for track in tracks:
            if track.get("ext") != extension or not track.get("url"):
                continue
            try:
                text = _download_track(track["url"], extension)
            except YouTubeRateLimited:
                rate_limited = True
                continue
            if text:
                return text, rate_limited
    return "", rate_limited


def _download_track(url: str, extension: str) -> str:
    try:
        with YoutubeDL(_youtube_options()) as ydl:
            response = ydl.urlopen(url)
            raw = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        if _is_rate_limit(exc):
            raise YouTubeRateLimited("YouTube timedtext HTTP 429") from exc
        raise

    if extension == "json3":
        return _parse_json3(raw)
    if extension == "vtt":
        return _parse_vtt(raw)
    return _strip_markup(raw)


def _parse_json3(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""

    chunks: list[str] = []
    for event in data.get("events", []):
        segment_text = "".join(seg.get("utf8", "") for seg in event.get("segs", []))
        segment_text = segment_text.strip()
        if segment_text:
            chunks.append(segment_text)
    return _normalize_transcript(" ".join(chunks))


def _parse_vtt(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        lines.append(line)
    return _normalize_transcript(" ".join(lines))


def _strip_markup(raw: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", raw)
    return _normalize_transcript(without_tags)


def _normalize_transcript(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
