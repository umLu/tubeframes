import unittest
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from unittest.mock import Mock, patch

import pandas as pd

from tubeframes import Search


class TestSearch(unittest.TestCase):

    def test_df_shape(self):
        df_shape = Search("Test", maxres=25).df
        self.assertTrue(df_shape.shape[0] >= 1)
        self.assertEqual(df_shape.shape[1], 14)

    def test_caption(self):
        df_caption = Search("Test", caption=True).df
        self.assertIsNotNone(df_caption)
        self.assertIn("video_caption", df_caption.columns)
        list_caption = df_caption["video_caption"].to_list()
        self.assertTrue(
            all(caption is None or isinstance(caption, str) for caption in list_caption)
        )

    def test_channel(self):
        df_channel = Search("Test", item_type="channel").df
        self.assertTrue(df_channel.shape[0] >= 1)
        self.assertEqual(df_channel.shape[1], 8)

    def test_big_shape(self):
        df_shape = Search("Test", maxres=100).df.shape
        self.assertTrue(df_shape[0] >= 50)


class TestSearchFilters(unittest.TestCase):

    def test_build_search_filters_maps_supported_options(self) -> None:
        filters = Search._build_search_filters(
            item_type="video",
            published_after=datetime(2024, 1, 1, 10, 0, 0),
            published_before=datetime(
                2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc
            ),
            region_code="US",
            relevance_language="en",
            order="date",
            video_duration="short",
            safe_search="strict",
            channel_id="channel_1",
        )

        self.assertEqual(filters["publishedAfter"], "2024-01-01T10:00:00Z")
        self.assertEqual(filters["publishedBefore"], "2024-01-02T10:00:00Z")
        self.assertEqual(filters["regionCode"], "US")
        self.assertEqual(filters["relevanceLanguage"], "en")
        self.assertEqual(filters["order"], "date")
        self.assertEqual(filters["videoDuration"], "short")
        self.assertEqual(filters["safeSearch"], "strict")
        self.assertEqual(filters["channelId"], "channel_1")

    def test_build_search_filters_rejects_invalid_order(self) -> None:
        with self.assertRaisesRegex(ValueError, "order"):
            Search._build_search_filters(
                item_type="video",
                published_after=None,
                published_before=None,
                region_code=None,
                relevance_language=None,
                order="popularity",
                video_duration=None,
                safe_search="none",
                channel_id=None,
            )

    def test_build_search_filters_rejects_video_duration_for_channel(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "video_duration"):
            Search._build_search_filters(
                item_type="channel",
                published_after=None,
                published_before=None,
                region_code=None,
                relevance_language=None,
                order="relevance",
                video_duration="short",
                safe_search="none",
                channel_id=None,
            )

    def test_search_request_includes_filter_params(self) -> None:
        search = Search.__new__(Search)
        search._developer_key = "key"
        search._search_filters = {
            "order": "date",
            "safeSearch": "strict",
            "regionCode": "US",
        }

        mock_client = Mock()
        mock_client.search.return_value.list.return_value.execute.return_value = {
            "items": []
        }

        with patch(
            "tubeframes.search.create_tubeframes_client",
            return_value=mock_client,
        ):
            search._search_request(
                term="python",
                maxres=10,
                page_token="TOKEN_1",
                item_type="video",
            )

        request_kwargs = mock_client.search.return_value.list.call_args.kwargs
        self.assertEqual(request_kwargs["order"], "date")
        self.assertEqual(request_kwargs["safeSearch"], "strict")
        self.assertEqual(request_kwargs["regionCode"], "US")
        self.assertEqual(request_kwargs["pageToken"], "TOKEN_1")


class TestSearchPagination(unittest.TestCase):

    def test_consolidate_search_respects_requested_remainder(self) -> None:
        search = Search.__new__(Search)
        calls: List[Tuple[int, Optional[str]]] = []

        def fake_search_from_term(
            _term: str,
            maxres: int,
            item_type: str = "video",
            page_token: Optional[str] = None,
        ) -> dict:
            _ = item_type
            calls.append((maxres, page_token))

            if page_token is None:
                return {"items": [], "nextPageToken": "PAGE_2"}
            return {"items": []}

        search._search_from_term = fake_search_from_term

        with patch("tubeframes.search.time.sleep", return_value=None):
            consolidated = search._consolidate_search(
                term="python", maxres=75, item_type="video"
            )

        self.assertEqual(len(consolidated), 2)
        self.assertEqual(calls[0][0], 50)
        self.assertEqual(calls[1][0], 25)
        self.assertEqual(calls[1][1], "PAGE_2")


class TestSearchCaptionIntegration(unittest.TestCase):

    def test_build_dataframe_keeps_video_rows_when_caption_fails(self) -> None:
        search = Search.__new__(Search)
        search._accepted_caption_lang = ["en"]
        search._developer_key = "key"
        search.raw = [
            {
                "items": [
                    {
                        "id": {"videoId": "vid1"},
                        "snippet": {
                            "title": "Title 1",
                            "publishedAt": "2022-01-01T00:00:00Z",
                        },
                    },
                    {
                        "id": {"videoId": "vid2"},
                        "snippet": {
                            "title": "Title 2",
                            "publishedAt": "2022-01-02T00:00:00Z",
                        },
                    },
                ]
            }
        ]

        mock_fetcher = Mock()
        mock_fetcher.fetch.side_effect = ["caption text", None]

        with patch(
            "tubeframes.search.get_video_statistics",
            return_value={
                "vid1": {
                    "viewCount": "10",
                    "likeCount": "2",
                    "commentCount": "1",
                },
                "vid2": {
                    "viewCount": "20",
                    "likeCount": "3",
                    "commentCount": "2",
                },
            },
        ), patch("tubeframes.search.CaptionFetcher", return_value=mock_fetcher):
            df = search._build_dataframe(item_type="video", caption=True)

        self.assertIsNotNone(df)
        self.assertEqual(df.loc["vid1", "video_caption"], "caption text")
        self.assertTrue(pd.isna(df.loc["vid2", "video_caption"]))
        self.assertIn("viewCount", df.columns)
        self.assertIn("likeCount", df.columns)
        mock_fetcher.emit_warning_summary.assert_called_once_with("Search")
