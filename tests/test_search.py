import unittest
from typing import List, Optional, Tuple
from unittest.mock import patch
from tubeframes import Search


class TestSearch(unittest.TestCase):

    def test_df_shape(self):
        df_shape = Search("Test", maxres=25).df
        self.assertTrue(df_shape.shape[0] >= 1)
        self.assertEqual(df_shape.shape[1], 13)

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
