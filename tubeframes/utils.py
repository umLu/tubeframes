from typing import List, Optional, Dict, Any
import os
import requests
import pandas as pd
from googleapiclient.discovery import build
import youtube_transcript_api as ytapi
from tubeframes.config.constants import YOUTUBE_API_SERVICE_NAME
from tubeframes.config.constants import YOUTUBE_API_VERSION
from tubeframes.config.constants import YOUTUBE_API_URL


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


def get_video_statistics(video_id: str, dev_key: str) -> Dict:
    """
    Get statistics for a video.

    Args:
        video_id: YouTube video ID
        dev_key: YouTube API developer key

    Returns:
        Dict: Video statistics
    """
    ploads = {"part": "statistics", "id": video_id, "key": dev_key}

    response = requests.get(YOUTUBE_API_URL, params=ploads, timeout=180)

    stats = response.json()
    return stats["items"][0]["statistics"]


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
