from typing import List, Optional, Dict, Any
import os
import warnings
import requests
import pandas as pd
from googleapiclient.discovery import build
import youtube_transcript_api as ytapi
from tubeframes.config.constants import (
    YOUTUBE_API_SERVICE_NAME,
    YOUTUBE_API_VERSION,
    YOUTUBE_API_URL,
    VIDEO_STATISTICS_TARGET_COLUMNS,
    YOUTUBE_API_MAX_PAGE_SIZE,
)


def _warn_statistics_unavailable(video_id: str) -> None:
    warnings.warn(
        f"Statistics unavailable for video_id={video_id}. "
        "Returning NA for statistics columns.",
        UserWarning,
        stacklevel=2,
    )


def get_dev_key(dev_key: Optional[str] = None) -> str:
    """
    Get YouTube developer key from parameter or environment variable.

    Args:
        dev_key: Provided developer key or None

    Returns:
        str: YouTube developer key

    Raises:
        ValueError: If no developer key is provided
    """
    if dev_key is None:
        try:
            dev_key = os.environ["YOUTUBE_DEVELOPER_KEY"]
        except KeyError as exc:
            raise ValueError("YouTube Developer Key not found") from exc
    return dev_key


def create_tubeframes_client(dev_key: str):
    """
    Create YouTube API client.

    Args:
        dev_key: YouTube API developer key

    Returns:
        object: YouTube API client
    """
    return build(
        YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=dev_key
    )


def get_video_captions(
    video_id: str, accepted_caption_lang: List[str]
) -> Optional[str]:
    """
    Get captions for a specific video.

    Args:
        video_id: YouTube video ID
        accepted_caption_lang: List of accepted languages for captions

    Returns:
        Optional[str]: Caption text or None if not available
    """
    try:
        if hasattr(ytapi.YouTubeTranscriptApi, "list_transcripts"):
            # Backward compatibility with older youtube_transcript_api versions.
            transcript_list = ytapi.YouTubeTranscriptApi.list_transcripts(
                video_id
            )
        else:
            transcript_api = ytapi.YouTubeTranscriptApi()
            transcript_list = transcript_api.list(video_id)

        for lang in accepted_caption_lang:
            try:
                transcript = transcript_list.find_transcript([lang])
                caption = transcript.fetch()
                df_caption = pd.DataFrame.from_dict(caption)
                return "; ".join(df_caption["text"])
            except ytapi._errors.NoTranscriptFound:
                continue
    except ytapi._errors.TranscriptsDisabled:
        return None
    return None


def _build_statistics_fallback() -> Dict[str, Optional[str]]:
    return {column: None for column in VIDEO_STATISTICS_TARGET_COLUMNS}


def _fetch_statistics(
    video_ids: List[str], dev_key: str
) -> Dict[str, Dict[str, Optional[str]]]:
    """Fetch statistics for a single videos.list batch.

    ``video_ids`` must have at most ``YOUTUBE_API_MAX_PAGE_SIZE`` entries.
    """
    params = {"part": "statistics", "id": ",".join(video_ids), "key": dev_key}

    try:
        response = requests.get(YOUTUBE_API_URL, params=params, timeout=180)
        response.raise_for_status()
        items = response.json()["items"]
        if not isinstance(items, list):
            raise TypeError("items payload is not a list")
    except (
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
    ):
        results: Dict[str, Dict[str, Optional[str]]] = {}
        for video_id in video_ids:
            _warn_statistics_unavailable(video_id)
            results[video_id] = _build_statistics_fallback()
        return results

    indexed: Dict[str, Dict[str, Optional[str]]] = {}
    fallback = _build_statistics_fallback()
    for item in items:
        if not isinstance(item, dict):
            continue
        video_id = item.get("id")
        statistics = item.get("statistics")
        if not isinstance(video_id, str) or not isinstance(statistics, dict):
            continue
        if any(column not in statistics for column in VIDEO_STATISTICS_TARGET_COLUMNS):
            _warn_statistics_unavailable(video_id)
            indexed[video_id] = {**fallback, **statistics}
        else:
            indexed[video_id] = statistics

    for video_id in video_ids:
        if video_id not in indexed:
            _warn_statistics_unavailable(video_id)
            indexed[video_id] = _build_statistics_fallback()

    return indexed


def get_video_statistics(
    video_ids: List[str], dev_key: str
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Fetch statistics for multiple videos in batches of up to
    ``YOUTUBE_API_MAX_PAGE_SIZE`` IDs per request.

    Args:
        video_ids: List of YouTube video IDs.
        dev_key: YouTube API developer key.

    Returns:
        Mapping video_id -> statistics dict. Every ID in ``video_ids`` is
        present in the result. IDs missing from the API response or whose
        target columns are incomplete receive the fallback dict (``None``
        for every column in ``VIDEO_STATISTICS_TARGET_COLUMNS``) and emit
        a ``UserWarning``.
    """
    if not video_ids:
        return {}

    results: Dict[str, Dict[str, Optional[str]]] = {}
    for start in range(0, len(video_ids), YOUTUBE_API_MAX_PAGE_SIZE):
        batch = video_ids[start : start + YOUTUBE_API_MAX_PAGE_SIZE]
        results.update(_fetch_statistics(batch, dev_key))
    return results


def process_thumbnails(
    snippet: Dict[str, Any], video_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Process video thumbnails and add to video info dictionary.

    Args:
        snippet: Video snippet data from YouTube API
        video_info: Dictionary with video information

    Returns:
        Dict: Updated video information with thumbnail URL
    """
    if "thumbnails" in snippet:
        thumbnails = snippet["thumbnails"]
        if "maxres" in thumbnails:
            video_info["thumbnailUrl"] = thumbnails["maxres"].get("url")
        elif "high" in thumbnails:
            video_info["thumbnailUrl"] = thumbnails["high"].get("url")
        elif "default" in thumbnails:
            video_info["thumbnailUrl"] = thumbnails["default"].get("url")
    return video_info


def create_df_from_items(items_data: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Create a DataFrame from a list of processed video items.

    Args:
        items_data: List of dictionaries with video information

    Returns:
        pd.DataFrame: DataFrame with video information
    """
    if not items_data:
        return pd.DataFrame()

    df = pd.DataFrame(items_data)

    # Convert publishedAt column to datetime
    if "publishedAt" in df.columns:
        df["publishedAt"] = pd.to_datetime(df["publishedAt"])

    return df
