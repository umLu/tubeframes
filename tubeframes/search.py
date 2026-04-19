from typing import List, Dict, Optional
import time
import requests
import pandas as pd
from googleapiclient.errors import HttpError


from tubeframes.utils import (
    get_dev_key,
    create_tubeframes_client,
    get_video_captions,
    get_video_statistics,
    process_thumbnails,
    create_df_from_items,
)


class Search:
    """Main class for YouTube search."""

    DEFAULT_MAX_RES = 50

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
        results = min(self.DEFAULT_MAX_RES, remaining_results)
        search_list = self._search_from_term(term, results, item_type)
        consolidated_search = [search_list]
        remaining_results -= results

        while "nextPageToken" in search_list and remaining_results > 0:
            time.sleep(0.1)  # Avoid request overload
            results = min(self.DEFAULT_MAX_RES, remaining_results)
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
        try:
            search_list = self._search_request(
                term, maxres, page_token, item_type
            )
            # Validate response
            if isinstance(search_list, dict):
                expected_keys = [
                    "kind", "etag", "regionCode", "pageInfo", "items"
                ]
                if not set(search_list.keys()).issuperset(set(expected_keys)):
                    raise KeyError("Missing expected keys in API response")
            else:
                raise TypeError("API response is not a dictionary")
        except HttpError as e:
            print(f"An HTTP error {e.resp.status} occurred:\n{e.content}")
            raise
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
        """
        items_data = []
        for search_req in self.raw:
            for search_item in search_req["items"]:
                try:
                    if item_type == "video":
                        id_key = "videoId"
                    elif item_type == "channel":
                        id_key = "channelId"
                    else:
                        continue

                    if not (
                        "id" in search_item
                        and id_key in search_item["id"]
                        and "snippet" in search_item
                    ):
                        continue

                    item_id = search_item["id"][id_key]
                    snippet = search_item["snippet"]

                    # Prepare basic video info from snippet
                    video_info = snippet.copy()
                    video_info[id_key] = item_id

                    # Process thumbnails
                    video_info = process_thumbnails(snippet, video_info)

                    if item_type == "video":
                        # Add statistics
                        item_stats = get_video_statistics(
                            item_id, self._developer_key
                        )
                        video_info.update(item_stats)

                        # Add captions if requested
                        if caption:
                            video_caption = get_video_captions(
                                item_id, self._accepted_caption_lang
                            )
                            video_info["video_caption"] = video_caption

                    items_data.append(video_info)

                except (
                    KeyError,
                    ValueError,
                    HttpError,
                    requests.RequestException,
                ):
                    continue

        df = create_df_from_items(items_data)

        if not df.empty:
            if item_type == "video":
                drop_columns = ["likeCount", "viewCount"]
                df.dropna(axis=0, how="any", inplace=True, subset=drop_columns)
                df = df.astype({"likeCount": int, "viewCount": int})

            df.set_index(id_key, inplace=True)
            return df
        else:
            print("No results. The DataFrame attribute will be None")
            return None
