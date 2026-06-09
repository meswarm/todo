"""Utilities for parsing embedded R2 media references in Markdown-like text."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse
from pathlib import Path
from typing import Literal


MediaKind = Literal["image", "video", "audio", "file"]

IMAGE_EXTENSIONS = frozenset({"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"})
VIDEO_EXTENSIONS = frozenset({"mp4", "mov", "mkv", "webm", "avi"})
AUDIO_EXTENSIONS = frozenset({"mp3", "wav", "m4a", "aac", "ogg", "flac"})


@dataclass(frozen=True)
class EmbeddedMedia:
    kind: MediaKind
    label: str
    url: str
    filename: str


_IMAGE_LINK_RE = re.compile(r"!\[(?P<label>[^\]]*)\]\((?P<url>r2://[^)\s]+)\)")
_LINK_RE = re.compile(r"(?<!\!)\[(?P<label>[^\]]+)\]\((?P<url>r2://[^)\s]+)\)")
_BARE_RE = re.compile(r"r2://[^\s\]\)\}\"';:>]+")
_BARE_TRAILING_PUNCTUATION = ".,!?:;)]}>"


def _infer_kind(filename: str) -> MediaKind:
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    return "file"


def _extract_filename(r2_url: str) -> str:
    parsed = urlparse(r2_url)
    parts = parsed.path.rsplit("/", 1)
    if len(parts) == 2:
        return unquote(parts[1])
    return ""


def _build_entry(url: str, label: str) -> EmbeddedMedia:
    filename = _extract_filename(url)
    return EmbeddedMedia(
        kind=_infer_kind(filename),
        label=label,
        url=url,
        filename=filename,
    )


def _clean_bare_url(raw_url: str) -> str:
    return raw_url.rstrip(_BARE_TRAILING_PUNCTUATION)


def parse_embedded_media(text: str) -> list[EmbeddedMedia]:
    """Parse embedded R2 media references from text and return ordered metadata."""

    found: list[tuple[int, EmbeddedMedia]] = []
    occupied: list[tuple[int, int]] = []

    def _add_match(match: re.Match[str], label: str, use_label: bool = True) -> None:
        span = match.span(0)
        resolved_label = label if label else _extract_filename(match.group("url"))
        if not use_label and not resolved_label:
            resolved_label = match.group("url")
        found.append((span[0], _build_entry(match.group("url"), resolved_label)))
        occupied.append(span)

    for match in _IMAGE_LINK_RE.finditer(text):
        _add_match(match, match.group("label"), use_label=True)

    for match in _LINK_RE.finditer(text):
        _add_match(match, match.group("label"), use_label=True)

    for match in _BARE_RE.finditer(text):
        if any(span[0] < match.end() and match.start() < span[1] for span in occupied):
            continue
        raw_url = _clean_bare_url(match.group(0))
        found.append((match.start(), _build_entry(raw_url, _extract_filename(raw_url))))

    return [media for _, media in sorted(found, key=lambda pair: pair[0])]


def extract_embedded_media_references(text: str) -> list[str]:
    """Extract original R2 media references in display order."""

    found: list[tuple[int, str]] = []
    occupied: list[tuple[int, int]] = []

    for match in _IMAGE_LINK_RE.finditer(text):
        found.append((match.start(), match.group(0)))
        occupied.append(match.span(0))

    for match in _LINK_RE.finditer(text):
        found.append((match.start(), match.group(0)))
        occupied.append(match.span(0))

    for match in _BARE_RE.finditer(text):
        if any(span[0] < match.end() and match.start() < span[1] for span in occupied):
            continue
        found.append((match.start(), _clean_bare_url(match.group(0))))

    return [reference for _, reference in sorted(found, key=lambda pair: pair[0])]
