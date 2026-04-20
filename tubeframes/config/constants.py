"""Constants used in modules."""

YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
YOUTUBE_API_URL = (
    "https://www.googleapis.com/youtube/" + YOUTUBE_API_VERSION + "/videos"
)
VIDEO_STATISTICS_TARGET_COLUMNS = ("likeCount", "viewCount")
# Hard limit imposed by the YouTube Data API v3 for list endpoints
YOUTUBE_API_MAX_PAGE_SIZE = 50
