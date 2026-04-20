import unittest
from unittest.mock import patch

from tubeframes.captions import CaptionFetcher
from tubeframes.config.constants import (
    CAPTION_MAX_RETRIES,
    CAPTION_RETRY_BACKOFF_SECONDS,
)


class TestCaptionFetcher(unittest.TestCase):

    def test_retry_backoff_applies_exponential_sleep(self) -> None:
        fetcher = CaptionFetcher()
        with patch.object(
            fetcher,
            "_fetch_from_transcript_api",
            side_effect=[("error", None)] * CAPTION_MAX_RETRIES
            + [("success", "caption")],
        ) as mocked_fetch, patch("tubeframes.captions.time.sleep") as mocked_sleep:
            caption = fetcher.fetch("video_1", ["en"])

        self.assertEqual(caption, "caption")
        self.assertEqual(mocked_fetch.call_count, CAPTION_MAX_RETRIES + 1)
        self.assertEqual(mocked_sleep.call_count, CAPTION_MAX_RETRIES)
        for attempt in range(CAPTION_MAX_RETRIES):
            expected_backoff = CAPTION_RETRY_BACKOFF_SECONDS * (2 ** attempt)
            mocked_sleep.assert_any_call(expected_backoff)

    def test_ip_block_exception_triggers_ytdlp_fallback(self) -> None:
        class FakeIpBlocked(Exception):
            pass

        fetcher = CaptionFetcher()
        with patch(
            "tubeframes.captions._IP_BLOCK_ERROR_TYPES",
            (FakeIpBlocked,),
        ), patch.object(
            CaptionFetcher,
            "_list_transcripts",
            side_effect=FakeIpBlocked("blocked"),
        ), patch.object(
            fetcher,
            "_fetch_with_ytdlp",
            return_value=("success", "caption from ytdlp"),
        ) as mocked_fallback:
            caption = fetcher.fetch("video_1", ["en"])

        self.assertEqual(caption, "caption from ytdlp")
        mocked_fallback.assert_called_once_with("video_1", ("en",))

    def test_fallback_timeout_is_reported(self) -> None:
        fetcher = CaptionFetcher()
        with patch.object(
            fetcher, "_fetch_with_retries", return_value=("blocked", None)
        ), patch.object(
            fetcher,
            "_fetch_with_ytdlp",
            return_value=("blocked_ytdlp_failed", None),
        ):
            caption = fetcher.fetch("video_1", ["en"])

        self.assertIsNone(caption)
        with self.assertWarnsRegex(
            UserWarning, "yt-dlp fallback failed"
        ):
            fetcher.emit_warning_summary("Search")

    def test_select_track_respects_language_priority(self) -> None:
        language_map = {
            "es": [{"url": "http://example.com/es", "ext": "json3"}],
            "en": [{"url": "http://example.com/en", "ext": "json3"}],
        }

        track = CaptionFetcher._select_track(language_map, ["pt", "en"])

        self.assertIsNotNone(track)
        self.assertEqual(track["url"], "http://example.com/en")

    def test_transcript_language_variant_is_supported(self) -> None:
        class FakeTranscript:
            def __init__(self, language_code: str) -> None:
                self.language_code = language_code

            @staticmethod
            def fetch() -> list:
                return [{"text": "hello world"}]

        fetcher = CaptionFetcher()
        with patch.object(
            CaptionFetcher,
            "_list_transcripts",
            return_value=[FakeTranscript("en-US")],
        ):
            caption = fetcher.fetch("video_1", ["en"])

        self.assertEqual(caption, "hello world")

    def test_fetch_uses_cache_per_instance(self) -> None:
        fetcher = CaptionFetcher()
        with patch.object(
            fetcher, "_fetch_with_retries", return_value=("success", "caption")
        ) as mocked_fetch:
            first = fetcher.fetch("video_1", ["en"])
            second = fetcher.fetch("video_1", ["en"])

        self.assertEqual(first, "caption")
        self.assertEqual(second, "caption")
        mocked_fetch.assert_called_once()

    def test_emit_warning_summary_aggregates_multiple_failures(self) -> None:
        fetcher = CaptionFetcher()
        with patch(
            "tubeframes.captions.CAPTION_WARNING_SAMPLE_SIZE",
            2,
        ), patch.object(
            fetcher, "_fetch_with_retries", return_value=("error", None)
        ):
            fetcher.fetch("video_1", ["en"])
            fetcher.fetch("video_2", ["en"])
            fetcher.fetch("video_3", ["en"])

        with self.assertWarnsRegex(
            UserWarning, "transcript API failed after retries: 3 video\\(s\\)"
        ):
            fetcher.emit_warning_summary("ChannelInfo")

    def test_expected_missing_caption_does_not_emit_warning(self) -> None:
        fetcher = CaptionFetcher()
        with patch.object(
            fetcher,
            "_fetch_with_retries",
            return_value=("expected_empty", None),
        ):
            caption = fetcher.fetch("video_1", ["en"])

        self.assertIsNone(caption)
        with patch("tubeframes.captions.warnings.warn") as mocked_warn:
            fetcher.emit_warning_summary("Search")
        mocked_warn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
