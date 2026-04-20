"""Constants used in modules."""

YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_API_URL = (
    "https://www.googleapis.com/youtube/" + YOUTUBE_API_VERSION + "/videos"
)
VIDEO_STATISTICS_TARGET_COLUMNS = ("likeCount", "viewCount")
# Hard limit imposed by the YouTube Data API v3 for list endpoints
YOUTUBE_API_MAX_PAGE_SIZE = 50

CAPTION_MAX_RETRIES = 2
CAPTION_RETRY_BACKOFF_SECONDS = 0.5
CAPTION_YTDLP_TIMEOUT_SECONDS = 30.0
CAPTION_WARNING_SAMPLE_SIZE = 5

SEARCH_ORDER_VALUES = ("date", "rating", "relevance", "viewCount")
SEARCH_VIDEO_DURATION_VALUES = ("short", "medium", "long")
SEARCH_SAFE_SEARCH_VALUES = ("none", "moderate", "strict")
SEARCH_DEFAULT_ORDER = "relevance"
SEARCH_DEFAULT_SAFE_SEARCH = "none"
