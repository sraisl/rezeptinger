from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape

from yt_dlp import YoutubeDL


class TranscriptUnavailable(Exception):
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
    options = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "extract_flat": False,
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

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


def _extract_transcript(info: dict) -> str:
    subtitles = info.get("subtitles") or {}
    auto_captions = info.get("automatic_captions") or {}

    for collection in (subtitles, auto_captions):
        for language in _preferred_languages(collection):
            text = _transcript_from_tracks(collection.get(language) or [])
            if text:
                return text

    return ""


def _preferred_languages(collection: dict) -> list[str]:
    preferred = ["de", "de-DE", "en", "en-US", "en-GB"]
    available = list(collection.keys())
    ordered = [language for language in preferred if language in collection]
    ordered.extend(language for language in available if language not in ordered)
    return ordered


def _transcript_from_tracks(tracks: list[dict]) -> str:
    for extension in ("json3", "vtt", "srv3", "ttml"):
        for track in tracks:
            if track.get("ext") != extension or not track.get("url"):
                continue
            text = _download_track(track["url"], extension)
            if text:
                return text
    return ""


def _download_track(url: str, extension: str) -> str:
    with YoutubeDL({"quiet": True}) as ydl:
        response = ydl.urlopen(url)
        raw = response.read().decode("utf-8", errors="replace")

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

