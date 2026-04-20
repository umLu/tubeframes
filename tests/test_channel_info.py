import unittest
from unittest.mock import Mock, patch

import pandas as pd

from tubeframes import ChannelInfo


class TestChannelInfo(unittest.TestCase):
    """Tests for the ChannelInfo class."""

    # Youtube channel ID for testing
    TEST_CHANNEL_ID = "UCBR8-60-B28hp2BmDPdntcQ"

    def test_init_with_list(self):
        """Tests initialization with channel ID as list."""
        channel_info = ChannelInfo([self.TEST_CHANNEL_ID], max_results=5)

        self.assertEqual(len(channel_info._channel_ids), 1)
        self.assertEqual(channel_info._channel_ids[0], self.TEST_CHANNEL_ID)

    def test_dataframe_structure(self):
        """Tests the structure of the resulting DataFrame."""
        channel_info = ChannelInfo(self.TEST_CHANNEL_ID, max_results=5)

        self.assertTrue(len(channel_info.df) > 0)

        expected_columns = {
            "channelId",
            "videoId",
            "title",
            "description",
            "publishedAt",
            "caption",
        }
        df_columns = channel_info.df.columns
        self.assertTrue(expected_columns.issubset(set(df_columns)))

    def test_captions(self):
        """Tests of captions."""
        channel_info = ChannelInfo(
            self.TEST_CHANNEL_ID, max_results=5, accepted_caption_lang=["pt", "en"]
        )

        self.assertIn("caption", channel_info.df.columns)


class TestChannelInfoCaptionIntegration(unittest.TestCase):

    def test_build_dataframe_keeps_video_rows_when_caption_fails(self) -> None:
        channel_info = ChannelInfo.__new__(ChannelInfo)
        channel_info._accepted_caption_lang = ["en"]
        channel_info.raw_data = {
            "channel_1": {
                "items": [
                    {
                        "snippet": {
                            "type": "upload",
                            "title": "Video 1",
                            "description": "Desc 1",
                            "publishedAt": "2022-01-01T00:00:00Z",
                        },
                        "contentDetails": {"upload": {"videoId": "vid1"}},
                    },
                    {
                        "snippet": {
                            "type": "upload",
                            "title": "Video 2",
                            "description": "Desc 2",
                            "publishedAt": "2022-01-02T00:00:00Z",
                        },
                        "contentDetails": {"upload": {"videoId": "vid2"}},
                    },
                ]
            }
        }

        mock_fetcher = Mock()
        mock_fetcher.fetch.side_effect = ["caption text", None]

        with patch(
            "tubeframes.channel_info.CaptionFetcher",
            return_value=mock_fetcher,
        ):
            df = channel_info._build_dataframe()

        self.assertEqual(len(df), 2)
        self.assertEqual(df.loc[0, "caption"], "caption text")
        self.assertTrue(pd.isna(df.loc[1, "caption"]))
        mock_fetcher.emit_warning_summary.assert_called_once_with(
            "ChannelInfo"
        )


if __name__ == "__main__":
    unittest.main()
