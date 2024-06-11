import datetime
from typing import TYPE_CHECKING, Any, List

from bs4 import Tag

from . import utils


if TYPE_CHECKING:
    from .works import Work


def __setifnotnone(obj: object, attr: str, value: Any) -> None:
    if value is not None:
        setattr(obj, attr, value)


def get_work_from_banner(work: Tag) -> Work:
    # * These imports need to be here to prevent circular imports
    # * (series.py would requite common.py and vice-versa)
    from .series import Series
    from .users import User
    from .works import Work

    authors: List[User] = []
    try:
        for a in work.h4.find_all("a"):  # type: ignore # Accounted for by except clause.
            if "rel" in a.attrs:
                if "author" in a["rel"]:
                    authors.append(User(a.string, load=False))
            elif a.attrs["href"].startswith("/works"):
                workname = a.string
                workid = utils.workid_from_url(a["href"])
    except AttributeError:
        pass

    new = Work(workid, load=False)

    fandoms: List[str] = []
    try:
        for a in work.find("h5", {"class": "fandoms"}).find_all("a"):  # type: ignore # Accounted for by except clause.
            fandoms.append(a.string)
    except AttributeError:
        pass

    warnings: List[str] = []
    relationships: List[str] = []
    characters: List[str] = []
    freeforms: List[str] = []
    try:
        for a in work.find(attrs={"class": "tags"}).find_all("li"):  # type: ignore # Accounted for by except clause.
            assert isinstance(a, Tag)
            if "warnings" in a["class"]:
                warnings.append(a.text)
            elif "relationships" in a["class"]:
                relationships.append(a.text)
            elif "characters" in a["class"]:
                characters.append(a.text)
            elif "freeforms" in a["class"]:
                freeforms.append(a.text)
    except AttributeError:
        pass

    reqtags = work.find(attrs={"class": "required-tags"})
    if reqtags is not None:
        assert isinstance(reqtags, Tag)
        rating = reqtags.find(attrs={"class": "rating"})
        if rating is not None:
            rating = rating.text
        categories = reqtags.find(attrs={"class": "category"})
        if categories is not None:
            categories = categories.text.split(", ")
    else:
        rating = categories = None

    summary = work.find(attrs={"class": "userstuff summary"})
    if summary is not None:
        summary = summary.text

    series: List[Series] = []
    series_list = work.find(attrs={"class": "series"})
    if series_list is not None:
        assert isinstance(series_list, Tag)
        for a in series_list.find_all("a"):
            seriesid = int(a.attrs["href"].split("/")[-1])
            seriesname = a.text
            s = Series(seriesid, load=False)
            s.name = seriesname
            series.append(s)

    stats = work.find(attrs={"class": "stats"})
    if stats is not None:
        assert isinstance(stats, Tag)
        language = stats.find("dd", {"class": "language"})
        if language is not None:
            language = language.text
        words = stats.find("dd", {"class": "words"})
        if words is not None:
            words = words.text.replace(",", "")
            words = int(words) if words.isdigit() else None
        bookmarks = stats.find("dd", {"class": "bookmarks"})
        if bookmarks is not None:
            bookmarks = bookmarks.text.replace(",", "")
            bookmarks = int(bookmarks) if bookmarks.isdigit() else None
        chapters = stats.find("dd", {"class": "chapters"})
        if chapters is not None:
            chapters = chapters.text.split("/")[0].replace(",", "")
            chapters = int(chapters) if chapters.isdigit() else None
        expected_chapters = stats.find("dd", {"class": "chapters"})
        if expected_chapters is not None:
            expected_chapters = expected_chapters.text.split("/")[-1].replace(",", "")
            expected_chapters = int(expected_chapters) if expected_chapters.isdigit() else None
        hits = stats.find("dd", {"class": "hits"})
        if hits is not None:
            hits = hits.text.replace(",", "")
            hits = int(hits) if hits.isdigit() else None
        kudos = stats.find("dd", {"class": "kudos"})
        if kudos is not None:
            kudos = kudos.text.replace(",", "")
            kudos = int(kudos) if kudos.isdigit() else None
        comments = stats.find("dd", {"class": "comments"})
        if comments is not None:
            comments = comments.text.replace(",", "")
            comments = int(comments) if comments.isdigit() else None
        restricted = work.find("img", {"title": "Restricted"}) is not None
        complete = None if chapters is None else (chapters == expected_chapters)
    else:
        language = words = bookmarks = chapters = expected_chapters = hits = restricted = complete = None

    date = work.find("p", {"class": "datetime"})
    date_updated = None if date is None else datetime.datetime.strptime(date.getText(), "%d %b %Y").astimezone()

    __setifnotnone(new, "authors", authors)
    __setifnotnone(new, "bookmarks", bookmarks)
    __setifnotnone(new, "categories", categories)
    __setifnotnone(new, "nchapters", chapters)
    __setifnotnone(new, "characters", characters)
    __setifnotnone(new, "complete", complete)
    __setifnotnone(new, "date_updated", date_updated)
    __setifnotnone(new, "expected_chapters", expected_chapters)
    __setifnotnone(new, "fandoms", fandoms)
    __setifnotnone(new, "hits", hits)
    __setifnotnone(new, "comments", comments)
    __setifnotnone(new, "kudos", kudos)
    __setifnotnone(new, "language", language)
    __setifnotnone(new, "rating", rating)
    __setifnotnone(new, "relationships", relationships)
    __setifnotnone(new, "restricted", restricted)
    __setifnotnone(new, "series", series)
    __setifnotnone(new, "summary", summary)
    __setifnotnone(new, "tags", freeforms)
    __setifnotnone(new, "title", workname)
    __setifnotnone(new, "warnings", warnings)
    __setifnotnone(new, "words", words)

    return new
