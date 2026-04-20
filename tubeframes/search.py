from typing import List, Dict, Optional, Tuple
import time
import pandas as pd


from tubeframes.captions import CaptionFetcher
from tubeframes.utils import (
    get_dev_key,
    create_tubeframes_client,
    get_video_statistics,
    process_thumbnails,
    create_df_from_items,
)
from tubeframes.config.constants import (
    VIDEO_STATISTICS_TARGET_COLUMNS,
    YOUTUBE_API_MAX_PAGE_SIZE,
)


class Search:
    """Main class for YouTube search."""

    def __init__(
        self,
        term: str,
        caption: bool = False,
        maxres: int = 50,
        accepted_caption_lang: Optional[List[str]] = None,
        item_type: str = "video",
        developer_key: Optional[str] = None,
    ) -> None:
        """
        Initialize the Search class.

        Args:
            term: YouTube search term
            caption: Whether to include captions
            maxres: Maximum number of results to return
            accepted_caption_lang: List of accepted languages for captions
            item_type: Type of item to search for ("video" or "channel")
            developer_key: YouTube API developer key
        """
        if accepted_caption_lang is None:
            accepted_caption_lang = ["pt", "en"]
        self._accepted_caption_lang = accepted_caption_lang
        self._developer_key = get_dev_key(developer_key)
        self.raw = self._consolidate_search(term, maxres, item_type)
        self.df = self._build_dataframe(
            item_type=item_type, caption=caption
        )

    def _consolidate_search(
        self, term: str, maxres: int, item_type: str
    ) -> List[Dict]:
        """
        Consolidate search results from multiple pages if needed.

        Args:
            term: Search term
            maxres: Maximum number of results
            item_type: Type of item to search for

        Returns:
            List[Dict]: List of search result pages
        """
        if maxres <= 0:
            return []

        remaining_results = maxres
        results = min(YOUTUBE_API_MAX_PAGE_SIZE, remaining_results)
        search_list = self._search_from_term(term, results, item_type)
        consolidated_search = [search_list]
        remaining_results -= results

        while "nextPageToken" in search_list and remaining_results > 0:
            time.sleep(0.1)  # Avoid request overload
            results = min(YOUTUBE_API_MAX_PAGE_SIZE, remaining_results)
            search_list = self._search_from_term(
                term,
                results,
                item_type=item_type,
                page_token=search_list["nextPageToken"],
            )
            consolidated_search.append(search_list)
            remaining_results -= results
        return consolidated_search

    def _search_from_term(
        self,
        term: str,
        maxres: int = 50,
        item_type: str = "video",
        page_token: Optional[str] = None,
    ) -> Dict:
        """
        Search YouTube with term.

        Args:
            term: Search term
            maxres: Maximum number of results
            item_type: Type of item to search for
            page_token: Token for pagination

        Returns:
            Dict: Search results

        Raises:
            HttpError: If API request fails
        """
        search_list = self._search_request(term, maxres, page_token, item_type)
        # Validate response
        if isinstance(search_list, dict):
            expected_keys = [
                "kind", "etag", "regionCode", "pageInfo", "items"
            ]
            if not set(search_list.keys()).issuperset(set(expected_keys)):
                raise KeyError("Missing expected keys in API response")
        else:
            raise TypeError("API response is not a dictionary")
        return search_list

    def _search_request(
        self,
        term: str,
        maxres: int = 50,
        page_token: Optional[str] = None,
        item_type: str = "video",
    ) -> Dict:
        """
        Query YouTube API.

        Args:
            term: Search term
            maxres: Maximum number of results
            page_token: Token for pagination
            item_type: Type of item to search for

        Returns:
            Dict: Search results
        """
        tubeframes_client = create_tubeframes_client(self._developer_key)
        search_response = (
            tubeframes_client.search()
            .list(
                q=term,
                part="id,snippet",
                maxResults=maxres,
                pageToken=page_token,
                type=item_type,
                safeSearch="none",
            )
            .execute()
        )
        return search_response

    def _build_dataframe(
        self, item_type: str = "video", caption: bool = False
    ) -> Optional[pd.DataFrame]:
        """
        Build a DataFrame from search results.

        Args:
            item_type: Type of item to search for
            caption: Whether to include captions

        Returns:
            Optional[pd.DataFrame]: DataFrame with search results or None

        Raises:
            ValueError: If ``item_type`` is not "video" or "channel".
        """
        id_key_by_type = {"video": "videoId", "channel": "channelId"}
        id_key = id_key_by_type.get(item_type)
        if id_key is None:
            raise ValueError("item_type must be 'video' or 'channel'")

        valid_items: List[Tuple[Dict, str]] = []
        for search_req in self.raw:
            for search_item in search_req.get("items", []):
                if not (
                    "id" in search_item
                    and id_key in search_item["id"]
                    and "snippet" in search_item
                ):
                    continue
                valid_items.append((search_item, search_item["id"][id_key]))

        stats_by_id: Dict[str, Dict[str, Optional[str]]] = {}
        if item_type == "video" and valid_items:
            stats_by_id = get_video_statistics(
                [item_id for _, item_id in valid_items], self._developer_key
            )

        caption_fetcher: Optional[CaptionFetcher] = None
        if item_type == "video" and caption:
            caption_fetcher = CaptionFetcher()

        items_data = []
        for search_item, item_id in valid_items:
            snippet = search_item["snippet"]

            video_info = snippet.copy()
            video_info[id_key] = item_id

            video_info = process_thumbnails(snippet, video_info)

            if item_type == "video":
                video_info.update(stats_by_id.get(item_id, {}))

                if caption and caption_fetcher is not None:
                    video_info["video_caption"] = caption_fetcher.fetch(
                        item_id, self._accepted_caption_lang
                    )

            items_data.append(video_info)

        if caption_fetcher is not None:
            caption_fetcher.emit_warning_summary("Search")

        df = create_df_from_items(items_data)

        if df.empty:
            return None

        if item_type == "video":
            for column in VIDEO_STATISTICS_TARGET_COLUMNS:
                df[column] = pd.to_numeric(
                    df[column], errors="coerce"
                ).astype("Int64")

        df.set_index(id_key, inplace=True)
        return df
