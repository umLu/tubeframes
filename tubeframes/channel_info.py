from datetime import datetime
from typing import List, Union, Dict, Optional
import pandas as pd

from tubeframes.captions import CaptionFetcher
from tubeframes.utils import (
    get_dev_key,
    create_tubeframes_client,
    get_video_statistics,
    process_thumbnails,
    create_df_from_items,
    format_datetime_to_rfc3339,
)


class ChannelInfo:
    """Class to get information about videos from YouTube channels."""

    def __init__(
        self,
        channel_ids: Union[str, List[str]],
        max_results: int = 10,
        accepted_caption_lang: Optional[List[str]] = None,
        developer_key: Optional[str] = None,
        published_after: Optional[datetime] = None,
        published_before: Optional[datetime] = None,
        region_code: Optional[str] = None,
    ) -> None:
        """
        Initialize the class to get information about videos from channels.

        Args:
            channel_ids: YouTube channel ID(s).
            max_results: Maximum number of results per channel.
            accepted_caption_lang: List of accepted languages for captions.
            developer_key: YouTube API developer key.
            published_after: Include only resources published at/after this datetime.
            published_before: Include only resources published before/at this datetime.
            region_code: ISO 3166-1 alpha-2 region code.
        """
        if accepted_caption_lang is not None:
            self._accepted_caption_lang = accepted_caption_lang
        else:
            self._accepted_caption_lang = ["pt", "en"]
        self._developer_key = get_dev_key(developer_key)

        if isinstance(channel_ids, str):
            channel_ids = [channel_ids]

        self._channel_ids = channel_ids
        self._max_results = max_results
        self._activity_filters = self._build_activity_filters(
            published_after=published_after,
            published_before=published_before,
            region_code=region_code,
        )
        self._youtube = create_tubeframes_client(self._developer_key)

        self.raw_data = self._fetch_channel_videos()
        self.df = self._build_dataframe()

    @staticmethod
    def _build_activity_filters(
        published_after: Optional[datetime],
        published_before: Optional[datetime],
        region_code: Optional[str],
    ) -> Dict[str, str]:
        filters: Dict[str, str] = {}
        published_after_str = format_datetime_to_rfc3339(published_after)
        if published_after_str is not None:
            filters["publishedAfter"] = published_after_str

        published_before_str = format_datetime_to_rfc3339(published_before)
        if published_before_str is not None:
            filters["publishedBefore"] = published_before_str

        if region_code:
            filters["regionCode"] = region_code

        return filters

    def _fetch_channel_videos(self) -> Dict:
        """
        Get videos from specified channels.

        Returns:
            Dict: Dictionary with data obtained from the API.
        """
        all_data = {}

        for channel_id in self._channel_ids:
            try:
                response = (
                    self._youtube.activities()
                    .list(
                        part="snippet,contentDetails",
                        channelId=channel_id,
                        maxResults=self._max_results,
                        **self._activity_filters,
                    )
                    .execute()
                )

                all_data[channel_id] = response
            except Exception as e:
                raise RuntimeError(
                    f"Error fetching videos for channel {channel_id}"
                ) from e

        return all_data

    def _build_dataframe(self) -> pd.DataFrame:
        """
        Build a DataFrame from the collected data.

        Returns:
            pd.DataFrame: DataFrame with video information, captions,
            and video statistics.
        """
        video_data = []
        caption_fetcher = CaptionFetcher()

        for channel_id, response in self.raw_data.items():
            if "items" not in response:
                continue

            for item in response["items"]:
                if item["snippet"]["type"] != "upload":
                    continue

                # Only process items that have a videoId
                if "upload" not in item.get("contentDetails", {}):
                    continue

                video_id = item["contentDetails"]["upload"].get("videoId")
                if not video_id:
                    continue

                # Extract information from snippet
                snippet = item["snippet"]

                # Build the dictionary with video information
                video_info = {
                    "channelId": channel_id,
                    "videoId": video_id,
                    "title": snippet.get("title"),
                    "description": snippet.get("description"),
                    "publishedAt": snippet.get("publishedAt"),
                    "caption": caption_fetcher.fetch(
                        video_id, self._accepted_caption_lang
                    ),
                }

                # Process thumbnails
                video_info = process_thumbnails(snippet, video_info)

                video_data.append(video_info)

        stats_by_id: Dict[str, Dict[str, Optional[str]]] = {}
        if video_data:
            video_ids = list(dict.fromkeys(info["videoId"] for info in video_data))
            stats_by_id = get_video_statistics(video_ids, self._developer_key)
            for video_info in video_data:
                video_info.update(
                    stats_by_id.get(video_info["videoId"], {})
                )

        caption_fetcher.emit_warning_summary("ChannelInfo")

        # Create DataFrame from collected items
        return create_df_from_items(video_data)
