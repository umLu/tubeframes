import os
import unittest
import warnings
from unittest.mock import Mock, patch

import pandas as pd
import requests

from tubeframes.utils import (
    get_dev_key,
    create_tubeframes_client,
    get_video_captions,
    get_video_statistics,
    create_df_from_items,
)
from tubeframes.config.constants import VIDEO_STATISTICS_TARGET_COLUMNS


class TestUtilsFunctions(unittest.TestCase):

    # YouTube video for test
    TEST_VIDEO_ID = "_GuOjXYl5ew"

    def setUp(self):
        """Set up the test environment."""
        # If YOUTUBE_DEVELOPER_KEY is not set in environment, skip tests
        if "YOUTUBE_DEVELOPER_KEY" not in os.environ:
            self.skipTest("YOUTUBE_DEVELOPER_KEY environment variable not set")
        self.developer_key = os.environ["YOUTUBE_DEVELOPER_KEY"]

    def test_get_dev_key_from_env(self):
        """Test getting developer key from environment."""
        key = get_dev_key()
        self.assertEqual(key, self.developer_key)

    def test_get_dev_key_from_param(self):
        """Test getting developer key from parameter."""
        test_key = "test_key_value"
        key = get_dev_key(test_key)
        self.assertEqual(key, test_key)

    def test_create_tubeframes_client(self):
        """Test creating tubeframes client."""
        client = create_tubeframes_client(self.developer_key)
        self.assertTrue(hasattr(client, "search"))
        self.assertTrue(hasattr(client, "videos"))
        self.assertTrue(hasattr(client, "activities"))

    def test_get_video_statistics_single(self):
        """Test batch statistics with a single real video."""
        stats_by_id = get_video_statistics(
            [self.TEST_VIDEO_ID], self.developer_key
        )
        self.assertIn(self.TEST_VIDEO_ID, stats_by_id)
        for column in VIDEO_STATISTICS_TARGET_COLUMNS:
            self.assertIn(column, stats_by_id[self.TEST_VIDEO_ID])

    def test_get_video_captions(self):
        """Test getting video captions."""
        captions = get_video_captions(self.TEST_VIDEO_ID, ["en"])
        self.assertTrue(captions is None or isinstance(captions, str))

    def test_create_df_from_items(self):
        """Test creating DataFrame from items."""
        # Test with empty list
        df = create_df_from_items([])
        self.assertTrue(df.empty)

        # Test with multiple items
        items = [
            {"title": "Video 1", "publishedAt": "2022-01-01T00:00:00Z"},
            {"title": "Video 2", "publishedAt": "2022-01-02T00:00:00Z"},
        ]
        df = create_df_from_items(items)
        self.assertEqual(len(df), 2)
        self.assertIn("title", df.columns)
        self.assertIn("publishedAt", df.columns)
        self.assertTrue(
            pd.api.types.is_datetime64_any_dtype(df["publishedAt"])
            or isinstance(df["publishedAt"].iloc[0], pd.Timestamp)
        )

        # Test with items missing publishedAt
        items = [{"title": "Video 1"}, {"title": "Video 2"}]
        df = create_df_from_items(items)
        self.assertEqual(len(df), 2)
        self.assertNotIn("publishedAt", df.columns)


class TestGetVideoStatistics(unittest.TestCase):

    FALLBACK = {column: None for column in VIDEO_STATISTICS_TARGET_COLUMNS}
    WARNING_RE = "Statistics unavailable for video_id="

    @staticmethod
    def _patched_get(payload: dict):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return patch("tubeframes.utils.requests.get", return_value=response)

    def test_empty_input_returns_empty_dict(self) -> None:
        """No IDs -> no API call and empty result."""
        with patch("tubeframes.utils.requests.get") as mocked:
            result = get_video_statistics([], "key")
        self.assertEqual(result, {})
        mocked.assert_not_called()

    def test_missing_id_in_response_gets_fallback(self) -> None:
        """IDs absent from the API payload receive the fallback + warning."""
        payload = {"items": []}
        with self._patched_get(payload):
            with self.assertWarnsRegex(UserWarning, self.WARNING_RE):
                result = get_video_statistics(["vid1"], "key")
        self.assertEqual(result, {"vid1": self.FALLBACK})

    def test_partial_statistics_fills_missing_columns_only(self) -> None:
        """Present columns preserved; missing target columns get None."""
        payload = {
            "items": [{"id": "vid1", "statistics": {"viewCount": "10"}}]
        }
        with self._patched_get(payload):
            with self.assertWarnsRegex(UserWarning, self.WARNING_RE):
                result = get_video_statistics(["vid1"], "key")
        self.assertEqual(
            result, {"vid1": {**self.FALLBACK, "viewCount": "10"}}
        )

    def test_full_statistics_returned_as_is(self) -> None:
        """All target columns present -> no warning, payload returned."""
        full = {column: "1" for column in VIDEO_STATISTICS_TARGET_COLUMNS}
        payload = {"items": [{"id": "vid1", "statistics": full}]}
        with self._patched_get(payload):
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                result = get_video_statistics(["vid1"], "key")
        self.assertEqual(result, {"vid1": full})

    def test_non_mapping_items_are_ignored(self) -> None:
        """Malformed non-dict entries do not crash statistics parsing."""
        full = {column: "1" for column in VIDEO_STATISTICS_TARGET_COLUMNS}
        payload = {"items": [None, "oops", {"id": "vid1", "statistics": full}]}
        with self._patched_get(payload):
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                result = get_video_statistics(["vid1"], "key")
        self.assertEqual(result, {"vid1": full})

    def test_chunking_splits_into_batches_of_50(self) -> None:
        """>50 IDs triggers multiple API calls."""
        ids = [f"vid{i}" for i in range(75)]
        full = {column: "0" for column in VIDEO_STATISTICS_TARGET_COLUMNS}
        payload_a = {"items": [{"id": vid, "statistics": full} for vid in ids[:50]]}
        payload_b = {"items": [{"id": vid, "statistics": full} for vid in ids[50:]]}
        response_a, response_b = Mock(), Mock()
        for resp, payload in ((response_a, payload_a), (response_b, payload_b)):
            resp.raise_for_status.return_value = None
            resp.json.return_value = payload
        with patch(
            "tubeframes.utils.requests.get",
            side_effect=[response_a, response_b],
        ) as mocked:
            result = get_video_statistics(ids, "key")
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(len(result), 75)

    def test_network_failure_falls_back_for_entire_batch(self) -> None:
        """Batch-level error -> fallback for every ID in the batch."""
        with patch(
            "tubeframes.utils.requests.get",
            side_effect=requests.ConnectionError("boom"),
        ):
            with self.assertWarns(UserWarning):
                result = get_video_statistics(["vid1", "vid2"], "key")
        self.assertEqual(
            result, {"vid1": self.FALLBACK, "vid2": self.FALLBACK}
        )


if __name__ == "__main__":
    unittest.main()
