import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="tubeframes",
    version="0.4.0",
    author="Luiz P.",
    author_email="umluiz@gmail.com",
    description=(
        "A Python package for retrieving YouTube data, including video "
        "statistics, captions, and channel information. TubeFrames outputs "
        "results in a user-friendly pandas DataFrame format, making it ideal "
        "for data analysis workflows — especially in Jupyter Notebooks."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/umLu/tubeframes",
    project_urls={
        "Bug Tracker": "https://github.com/umLu/tubeframes/issues",
        "Documentation": "https://github.com/umLu/tubeframes#readme",
        "Source Code": "https://github.com/umLu/tubeframes",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Multimedia :: Video",
        "Topic :: Text Processing :: Linguistic",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Education",
        "Development Status :: 4 - Beta",
    ],
    keywords=(
        "youtube data caption video statistics analysis research "
        "dataframe pandas api channel transcript subtitle"
    ),
    packages=setuptools.find_packages(),
    install_requires=[
        "google-api-python-client",
        "pandas",
        "requests",
        "youtube_transcript_api",
        "yt-dlp",
    ],
    python_requires=">=3.9",
)
