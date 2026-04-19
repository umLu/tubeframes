"""
TubeFrames - A YouTube Data Analysis Library

A Python package for retrieving YouTube data, including video statistics, captions, and channel information. TubeFrames outputs results in a user-friendly pandas DataFrame format, making it ideal for data analysis workflows — especially in Jupyter Notebooks.
"""

from tubeframes.search import Search
from tubeframes.channel_info import ChannelInfo

__version__ = "0.3.3"
__license__ = "GNU General Public License v3 (GPLv3)"
__url__ = "https://github.com/umLu/tubeframes"
__all__ = ["Search", "ChannelInfo"]
