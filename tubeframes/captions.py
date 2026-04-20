from collections import defaultdict
import re
import time
from typing import (
    DefaultDict,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
)
import warnings

import requests
import youtube_transcript_api as ytapi
from yt_dlp import YoutubeDL
from tubeframes.config.constants import (
    CAPTION_MAX_RETRIES,
    CAPTION_RETRY_BACKOFF_SECONDS,
    CAPTION_YTDLP_TIMEOUT_SECONDS,
    CAPTION_WARNING_SAMPLE_SIZE,
)


_FETCH_SUCCESS = "success"
_FETCH_EXPECTED_EMPTY = "expected_empty"
_FETCH_BLOCKED = "blocked"
_FETCH_ERROR = "error"

_REASON_TRANSCRIPT_API_ERROR = "transcript_api_error"
_REASON_YTDLP_FAILED = "blocked_ytdlp_failed"

_FAILURE_REASON_LABELS = {
    _REASON_TRANSCRIPT_API_ERROR: "transcript API failed after retries",
    _REASON_YTDLP_FAILED: "IP blocked and yt-dlp fallback failed",
}


def _resolve_error_class(error_name: str) -> Optional[type]:
    # Support both legacy and current youtube_transcript_api exports.
    candidates = [getattr(ytapi, error_name, None)]
    error_module = getattr(ytapi, "_errors", None)
    if error_module is not None:
        candidates.append(getattr(error_module, error_name, None))

    for error_type in candidates:
        if isinstance(error_type, type) and issubclass(error_type, Exception):
            return error_type
    return None


_IP_BLOCK_ERROR_TYPES: Tuple[type, ...] = tuple(
    error_type
    for error_type in (
        _resolve_error_class("IpBlocked"),
        _resolve_error_class("RequestBlocked"),
    )
    if error_type is not None
)
_EXPECTED_EMPTY_ERROR_TYPES: Tuple[type, ...] = tuple(
    error_type
    for error_type in (
        _resolve_error_class("NoTranscriptFound"),
        _resolve_error_class("TranscriptsDisabled"),
    )
    if error_type is not None
)


class CaptionFetcher:
    """Caption collector with retry/backoff and yt-dlp fallback."""

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, Tuple[str, ...]], Optional[str]] = {}
        self._failures_by_reason: DefaultDict[str, List[str]] = defaultdict(list)

    def fetch(
        self, video_id: str, accepted_caption_lang: Sequence[str]
    ) -> Optional[str]:
        """Fetch caption text for a video while caching results per instance."""
        clean_langs = tuple(
            lang.strip()
            for lang in accepted_caption_lang
            if isinstance(lang, str) and lang.strip()
        )
        cache_key = (video_id, clean_langs)
        if cache_key in self._cache:
            return self._cache[cache_key]

        state, caption = self._fetch_with_retries(video_id, clean_langs)
        if state == _FETCH_SUCCESS:
            self._cache[cache_key] = caption
            return caption

        if state == _FETCH_EXPECTED_EMPTY:
            self._cache[cache_key] = None
            return None

        if state == _FETCH_BLOCKED:
            fallback_reason, fallback_caption = self._fetch_with_ytdlp(
                video_id, clean_langs
            )
            if fallback_caption is not None:
                self._cache[cache_key] = fallback_caption
                return fallback_caption
            self._record_failure(video_id, fallback_reason)
            self._cache[cache_key] = None
            return None

        self._record_failure(video_id, _REASON_TRANSCRIPT_API_ERROR)
        self._cache[cache_key] = None
        return None

    def emit_warning_summary(self, context: str) -> None:
        """Emit one warning with grouped failures for the current execution."""
        if not self._failures_by_reason:
            return

        reason_summaries = []
        for reason in sorted(self._failures_by_reason):
            video_ids = self._failures_by_reason[reason]
            sample = ", ".join(video_ids[:CAPTION_WARNING_SAMPLE_SIZE])
            reason_label = _FAILURE_REASON_LABELS.get(reason, reason)
            reason_summaries.append(
                f"{reason_label}: {len(video_ids)} video(s) [sample: {sample}]"
            )

        warnings.warn(
            f"{context} caption retrieval had failures. "
            + "; ".join(reason_summaries),
            UserWarning,
            stacklevel=2,
        )

    def _fetch_with_retries(
        self, video_id: str, accepted_caption_lang: Sequence[str]
    ) -> Tuple[str, Optional[str]]:
        for attempt in range(CAPTION_MAX_RETRIES + 1):
            state, caption = self._fetch_from_transcript_api(
                video_id, accepted_caption_lang
            )
            if state != _FETCH_ERROR:
                return state, caption

            if attempt < CAPTION_MAX_RETRIES:
                time.sleep(CAPTION_RETRY_BACKOFF_SECONDS * (2 ** attempt))

        return _FETCH_ERROR, None

    def _fetch_from_transcript_api(
        self, video_id: str, accepted_caption_lang: Sequence[str]
    ) -> Tuple[str, Optional[str]]:
        try:
            transcript_list = self._list_transcripts(video_id)
        except Exception as exc:
            if self._is_ip_block_error(exc):
                return _FETCH_BLOCKED, None
            if self._is_expected_empty_error(exc):
                return _FETCH_EXPECTED_EMPTY, None
            return _FETCH_ERROR, None

        for lang in accepted_caption_lang:
            try:
                transcript = transcript_list.find_transcript([lang])
                caption = transcript.fetch()
                caption_text = self._segments_to_text(caption)
                if caption_text is not None:
                    return _FETCH_SUCCESS, caption_text
            except Exception as exc:
                if self._is_ip_block_error(exc):
                    return _FETCH_BLOCKED, None
                if self._is_expected_empty_error(exc):
                    continue
                return _FETCH_ERROR, None

        return _FETCH_EXPECTED_EMPTY, None

    @staticmethod
    def _list_transcripts(video_id: str) -> object:
        if hasattr(ytapi.YouTubeTranscriptApi, "list_transcripts"):
            return ytapi.YouTubeTranscriptApi.list_transcripts(video_id)
        transcript_api = ytapi.YouTubeTranscriptApi()
        return transcript_api.list(video_id)

    @staticmethod
    def _is_ip_block_error(error: Exception) -> bool:
        return isinstance(error, _IP_BLOCK_ERROR_TYPES)

    @staticmethod
    def _is_expected_empty_error(error: Exception) -> bool:
        return isinstance(error, _EXPECTED_EMPTY_ERROR_TYPES)

    @staticmethod
    def _segments_to_text(segments: object) -> Optional[str]:
        if not isinstance(segments, list):
            return None
        return CaptionFetcher._join_clean_texts(
            segment.get("text") for segment in segments
            if isinstance(segment, dict)
        )

    @staticmethod
    def _join_clean_texts(raw_texts: Iterable[object]) -> Optional[str]:
        parts = []
        for text in raw_texts:
            if not isinstance(text, str):
                continue
            clean_text = text.replace("\n", " ").strip()
            if clean_text:
                parts.append(clean_text)
        if not parts:
            return None
        return "; ".join(parts)

    def _fetch_with_ytdlp(
        self, video_id: str, accepted_caption_lang: Sequence[str]
    ) -> Tuple[str, Optional[str]]:
        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": CAPTION_YTDLP_TIMEOUT_SECONDS,
        }

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False,
                )
        except Exception:
            return _REASON_YTDLP_FAILED, None

        caption = self._extract_caption_from_info(info, accepted_caption_lang)
        if caption is not None:
            return _FETCH_SUCCESS, caption
        return _REASON_YTDLP_FAILED, None

    def _extract_caption_from_info(
        self, info: object, accepted_caption_lang: Sequence[str]
    ) -> Optional[str]:
        if not isinstance(info, dict):
            return None

        language_maps = []
        subtitles = info.get("subtitles")
        automatic_captions = info.get("automatic_captions")
        if isinstance(subtitles, dict):
            language_maps.append(subtitles)
        if isinstance(automatic_captions, dict):
            language_maps.append(automatic_captions)

        for language_map in language_maps:
            track = self._select_track(language_map, accepted_caption_lang)
            if track is None:
                continue
            subtitle_text = self._download_track(track)
            if subtitle_text is not None:
                return subtitle_text

        return None

    @staticmethod
    def _select_track(
        language_map: Dict[str, object], accepted_caption_lang: Sequence[str]
    ) -> Optional[Dict[str, str]]:
        for lang in accepted_caption_lang:
            lang_lower = lang.lower()
            variant_track = None

            for code, entries in language_map.items():
                if not isinstance(code, str):
                    continue
                code_lower = code.lower()
                if code_lower == lang_lower:
                    track = CaptionFetcher._pick_preferred_track(entries)
                    if track is not None:
                        return track
                if code_lower.startswith(f"{lang_lower}-") or code_lower.startswith(
                    f"{lang_lower}_"
                ):
                    variant_track = CaptionFetcher._pick_preferred_track(entries)

            if variant_track is not None:
                return variant_track
        return None

    @staticmethod
    def _pick_preferred_track(entries: object) -> Optional[Dict[str, str]]:
        if not isinstance(entries, list):
            return None

        valid_tracks = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = entry.get("url")
            ext = entry.get("ext", "")
            if isinstance(url, str) and isinstance(ext, str):
                valid_tracks.append({"url": url, "ext": ext})

        if not valid_tracks:
            return None

        valid_tracks.sort(
            key=lambda track: 0 if track.get("ext") == "json3" else 1
        )
        return valid_tracks[0]

    def _download_track(self, track: Dict[str, str]) -> Optional[str]:
        try:
            response = requests.get(track["url"], timeout=CAPTION_YTDLP_TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException:
            return None

        if track["ext"] == "json3":
            try:
                return self._json3_to_text(response.json())
            except ValueError:
                return None
        return self._subtitle_text_to_plain(response.text)

    @staticmethod
    def _json3_to_text(payload: object) -> Optional[str]:
        if not isinstance(payload, dict):
            return None

        events = payload.get("events")
        if not isinstance(events, list):
            return None

        def _iter_utf8() -> Iterable[object]:
            for event in events:
                if not isinstance(event, dict):
                    continue
                segs = event.get("segs")
                if not isinstance(segs, list):
                    continue
                for seg in segs:
                    if isinstance(seg, dict):
                        yield seg.get("utf8")

        return CaptionFetcher._join_clean_texts(_iter_utf8())

    @staticmethod
    def _subtitle_text_to_plain(payload: str) -> Optional[str]:
        parts = []
        for raw_line in payload.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line == "WEBVTT" or "-->" in line or line.isdigit():
                continue
            if line.startswith("NOTE") or line.startswith("Kind:"):
                continue
            if line.startswith("Language:"):
                continue
            clean_line = re.sub(r"<[^>]+>", "", line).strip()
            if clean_line:
                parts.append(clean_line)

        if not parts:
            return None
        return "; ".join(parts)

    def _record_failure(self, video_id: str, reason: str) -> None:
        failures = self._failures_by_reason[reason]
        if video_id not in failures:
            failures.append(video_id)
