import functools
import itertools
import pickle
from pathlib import Path
from threading import Thread
from typing import Dict, List

from bs4 import BeautifulSoup, Tag

from .requester import requester
from .threadable import threadable
from .utils import UnexpectedResponseError


def _download_languages() -> None:
    languages: list[tuple[str, str]] = []
    url = "https://archiveofourown.org/languages"
    print(f"Downloading from {url}")
    try:
        # Get the languages.
        req = requester.request("get", url)
        soup = BeautifulSoup(req.content, "lxml")
        if isinstance(language_group := soup.find("dl", {"class": "language index group"}), Tag):
            for dt in language_group.find_all("dt"):
                alias = dt.a.attrs["href"].split("/")[-1] if dt.a is not None else None
                languages.append((dt.get_text(), alias))
    except AttributeError as err:
        msg = "Couldn't download the desired resource. Do you have the latest version of ao3-api?"
        raise UnexpectedResponseError(msg) from err
    else:
        # Add the languages to a file.
        language_path = Path(__file__).parent / "resources" / "languages"
        if not language_path.is_dir():
            language_path.mkdir(parents=True)
        with (language_path / "languages.pkl").open("wb") as file:
            pickle.dump(languages, file)
        print(f"Download complete ({len(languages)} languages)")


def _download_fandom(fandom_key: str, name: str) -> None:
    fandoms: list[str] = []
    url = f"https://archiveofourown.org/media/{fandom_key}/fandoms"
    print(f"Downloading from {url}")
    try:
        req = requester.request("get", url)
        soup = BeautifulSoup(req.content, "lxml")
        if isinstance(fandom_group := soup.find("ol", {"class": "alphabet fandom index group"}), Tag):
            for fandom in fandom_group.find_all("a", {"class": "tag"}):
                fandoms.append(fandom.get_text())
    except AttributeError as err:
        msg = "Couldn't download the desired resource. Do you have the latest version of ao3-api?"
        raise UnexpectedResponseError(msg) from err
    else:
        # Add the fandom to a file.
        fandom_path = Path(__file__).parent / "resources" / "fandoms"
        if not fandom_path.is_dir():
            fandom_path.mkdir(parents=True)
        with (fandom_path / f"{name}.pkl").open("wb") as file:
            pickle.dump(fandoms, file)
        print(f"Download complete ({len(fandoms)} fandoms)")


_FANDOM_RESOURCES = {
    "anime_manga_fandoms": functools.partial(
        _download_fandom,
        "Anime%20*a*%20Manga",
        "anime_manga_fandoms",
    ),
    "books_literature_fandoms": functools.partial(
        _download_fandom,
        "Books%20*a*%20Literature",
        "books_literature_fandoms",
    ),
    "cartoons_comics_graphicnovels_fandoms": functools.partial(
        _download_fandom,
        "Cartoons%20*a*%20Comics%20*a*%20Graphic%20Novels",
        "cartoons_comics_graphicnovels_fandoms",
    ),
    "celebrities_real_people_fandoms": functools.partial(
        _download_fandom,
        "Celebrities%20*a*%20Real%20People",
        "celebrities_real_people_fandoms",
    ),
    "movies_fandoms": functools.partial(
        _download_fandom,
        "Movies",
        "movies_fandoms",
    ),
    "music_bands_fandoms": functools.partial(
        _download_fandom,
        "Music%20*a*%20Bands",
        "music_bands_fandoms",
    ),
    "other_media_fandoms": functools.partial(
        _download_fandom,
        "Other%20Media",
        "other_media_fandoms",
    ),
    "theater_fandoms": functools.partial(
        _download_fandom,
        "Theater",
        "theater_fandoms",
    ),
    "tvshows_fandoms": functools.partial(
        _download_fandom,
        "TV%20Shows",
        "tvshows_fandoms",
    ),
    "videogames_fandoms": functools.partial(
        _download_fandom,
        "Video%20Games",
        "videogames_fandoms",
    ),
    "uncategorized_fandoms": functools.partial(
        _download_fandom,
        "Uncategorized%20Fandoms",
        "uncategorized_fandoms",
    ),
}

_LANGUAGE_RESOURCES = {
    "languages": _download_languages,
}

_RESOURCE_DICTS = [("fandoms", _FANDOM_RESOURCES), ("languages", _LANGUAGE_RESOURCES)]


@threadable
def download(resource: str) -> None:
    """Downloads the specified resource.
    This function is threadable.

    Args:
        resource (str): Resource name

    Raises:
        KeyError: Invalid resource
    """

    for _, resource_dict in _RESOURCE_DICTS:
        if resource in resource_dict:
            resource_dict[resource]()
            return
    msg = f"'{resource}' is not a valid resource"
    raise KeyError(msg)


def get_resources() -> Dict[str, List[str]]:
    """Returns a list of every resource available for download"""
    d: Dict[str, List[str]] = {name: list(resource_dict.keys()) for name, resource_dict in _RESOURCE_DICTS}
    return d


def has_resource(resource: str) -> bool:
    """Returns True if resource was already download, False otherwise"""
    path = Path(__file__).parent / "resources"
    return len(list(path.rglob(f"{resource}.pkl"))) > 0


@threadable
def download_all(redownload: bool = False) -> None:
    """Downloads every available resource.
    This function is threadable."""

    types = get_resources()
    for rsrc in itertools.chain(*types.values()):
        if redownload or not has_resource(rsrc):
            download(rsrc)


@threadable
def download_all_threaded(redownload: bool = False) -> None:
    """Downloads every available resource in parallel (about ~3.7x faster).
    This function is threadable."""

    threads: List[Thread] = []
    types = get_resources()
    for rsrc in itertools.chain(*types.values()):
        if redownload or not has_resource(rsrc):
            threads.append(download(rsrc, threaded=True))
    for thread in threads:
        thread.join()
