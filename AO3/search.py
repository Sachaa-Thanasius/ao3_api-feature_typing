from math import ceil
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from .common import get_work_from_banner
from .requester import requester
from .threadable import threadable
from .utils import Constraint, HTTPError


if TYPE_CHECKING:
    from .session import GuestSession
    from .works import Work


DEFAULT = "_score"
BEST_MATCH = "_score"
AUTHOR = "authors_to_sort_on"
TITLE = "title_to_sort_on"
DATE_POSTED = "created_at"
DATE_UPDATED = "revised_at"
WORD_COUNT = "word_count"
RATING = "rating_ids"
HITS = "hits"
BOOKMARKS = "bookmarks_count"
COMMENTS = "comments_count"
KUDOS = "kudos_count"

DESCENDING = "desc"
ASCENDING = "asc"


class Search:
    def __init__(
        self,
        any_field: Optional[str] = "",
        title: str = "",
        author: str = "",
        single_chapter: bool = False,
        word_count: Optional[Constraint] = None,
        language: str = "",
        fandoms: str = "",
        rating: Optional[int] = None,
        hits: Optional[Constraint] = None,
        kudos: Optional[Constraint] = None,
        crossovers: Optional[bool] = None,
        bookmarks: Optional[Constraint] = None,
        excluded_tags: str = "",
        comments: Optional[Constraint] = None,
        completion_status: Optional[bool] = None,
        page: int = 1,
        sort_column: str = "",
        sort_direction: str = "",
        revised_at: str = "",
        characters: str = "",
        relationships: str = "",
        tags: str = "",
        session: Optional[GuestSession] = None,
    ) -> None:
        self.any_field = any_field
        self.title = title
        self.author = author
        self.single_chapter = single_chapter
        self.word_count = word_count
        self.language = language
        self.fandoms = fandoms
        self.characters = characters
        self.relationships = relationships
        self.tags = tags
        self.rating = rating
        self.hits = hits
        self.kudos = kudos
        self.crossovers = crossovers
        self.bookmarks = bookmarks
        self.excluded_tags = excluded_tags
        self.comments = comments
        self.completion_status = completion_status
        self.page = page
        self.sort_column = sort_column
        self.sort_direction = sort_direction
        self.revised_at = revised_at

        self.session = session

        self.results: Optional[List[Work]] = None
        self.pages: int = 0
        self.total_results: int = 0

    @threadable
    def update(self) -> None:
        """Sends a request to the AO3 website with the defined search parameters, and updates all info.
        This function is threadable.
        """

        soup = search(
            self.any_field,
            self.title,
            self.author,
            self.single_chapter,
            self.word_count,
            self.language,
            self.fandoms,
            self.rating,
            self.hits,
            self.kudos,
            self.crossovers,
            self.bookmarks,
            self.excluded_tags,
            self.comments,
            self.completion_status,
            self.page,
            self.sort_column,
            self.sort_direction,
            self.revised_at,
            self.session,
            self.characters,
            self.relationships,
            self.tags,
        )

        results = soup.find("ol", {"class": ("work", "index", "group")})
        if (
            results is None
            and soup.find("p", text="No results found. You may want to edit your search to make it less specific.")
            is not None
        ):
            self.results = []
            self.total_results = 0
            self.pages = 0
            return
        assert isinstance(results, Tag)

        works: List[Work] = []
        for work in results.find_all("li", {"role": "article"}):
            assert isinstance(work, Tag)
            if work.h4 is None:
                continue

            new = get_work_from_banner(work)
            new._session = self.session
            works.append(new)

        self.results = works
        main_div = soup.find("div", {"class": "works-search region", "id": "main"})
        if isinstance(main_div, Tag):
            self.total_results = int(
                main_div.find("h3", {"class": "heading"})
                .get_text()
                .replace(",", "")
                .replace(".", "")
                .strip()
                .split(" ")[0],
            )
        self.pages = ceil(self.total_results / 20)


def search(
    any_field: Optional[str] = "",
    title: str = "",
    author: str = "",
    single_chapter: bool = False,
    word_count: Optional[Constraint] = None,
    language: str = "",
    fandoms: str = "",
    rating: Optional[int] = None,
    hits: Optional[Constraint] = None,
    kudos: Optional[Constraint] = None,
    crossovers: Optional[bool] = None,
    bookmarks: Optional[Constraint] = None,
    excluded_tags: str = "",
    comments: Optional[Constraint] = None,
    completion_status: Optional[bool] = None,
    page: int = 1,
    sort_column: str = "",
    sort_direction: str = "",
    revised_at: str = "",
    session: Optional[GuestSession] = None,
    characters: str = "",
    relationships: str = "",
    tags: str = "",
) -> BeautifulSoup:
    """Returns the results page for the search as a Soup object

    Args:
        any_field (str, optional): Generic search. Defaults to "".
        title (str, optional): Title of the work. Defaults to "".
        author (str, optional): Authors of the work. Defaults to "".
        single_chapter (bool, optional): Only include one-shots. Defaults to False.
        word_count (AO3.utils.Constraint, optional): Word count. Defaults to None.
        language (str, optional): Work language. Defaults to "".
        fandoms (str, optional): Fandoms included in the work. Defaults to "".
        characters (str, optional): Characters included in the work. Defaults to "".
        relationships (str, optional): Relationships included in the work. Defaults to "".
        tags (str, optional): Additional tags applied to the work. Defaults to "".
        rating (int, optional): Rating for the work. 9 for Not Rated, 10 for General Audiences,
        11 for Teen And Up Audiences, 12 for Mature, 13 for Explicit. Defaults to None.
        hits (AO3.utils.Constraint, optional): Number of hits. Defaults to None.
        kudos (AO3.utils.Constraint, optional): Number of kudos. Defaults to None.
        crossovers (bool, optional): If specified, if false, exclude crossovers, if true, include only crossovers
        bookmarks (AO3.utils.Constraint, optional): Number of bookmarks. Defaults to None.
        excluded_tags (str, optional): Tags to exclude. Defaults to "".
        comments (AO3.utils.Constraint, optional): Number of comments. Defaults to None.
        page (int, optional): Page number. Defaults to 1.
        sort_column (str, optional): Which column to sort on. Defaults to "".
        sort_direction (str, optional): Which direction to sort. Defaults to "".
        revised_at (str, optional): Show works older / more recent than this date. Defaults to "".
        session (AO3.Session, optional): Session object. Defaults to None.

    Returns:
        bs4.BeautifulSoup: Search result's soup
    """

    query_dict: Dict[str, Any] = {}
    query_dict["work_search[query]"] = any_field if any_field else " "
    if page != 1:
        query_dict["page"] = page
    if title != "":
        query_dict["work_search[title]"] = title
    if author != "":
        query_dict["work_search[creators]"] = author
    if single_chapter:
        query_dict["work_search[single_chapter]"] = 1
    if word_count:
        query_dict["work_search[word_count]"] = str(word_count)
    if language != "":
        query_dict["work_search[language_id]"] = language
    if fandoms != "":
        query_dict["work_search[fandom_names]"] = fandoms
    if characters != "":
        query_dict["work_search[character_names]"] = characters
    if relationships != "":
        query_dict["work_search[relationship_names]"] = relationships
    if tags != "":
        query_dict["work_search[freeform_names]"] = tags
    if rating is not None:
        query_dict["work_search[rating_ids]"] = rating
    if hits:
        query_dict["work_search[hits]"] = str(hits)
    if kudos:
        query_dict["work_search[kudos_count]"] = str(kudos)
    if crossovers is not None:
        query_dict["work_search[crossover]"] = "T" if crossovers else "F"
    if bookmarks:
        query_dict["work_search[bookmarks_count]"] = str(bookmarks)
    if excluded_tags:
        query_dict["work_search[excluded_tag_names]"] = excluded_tags
    if comments:
        query_dict["work_search[comments_count]"] = str(comments)
    if completion_status is not None:
        query_dict["work_search[complete]"] = "T" if completion_status else "F"
    if sort_column:
        query_dict["work_search[sort_column]"] = sort_column
    if sort_direction:
        query_dict["work_search[sort_direction]"] = sort_direction
    if revised_at:
        query_dict["work_search[revised_at]"] = revised_at

    url = f"https://archiveofourown.org/works/search?{urlencode(query_dict)}"

    req = requester.request("get", url) if session is None else session.get(url)
    if req.status_code == 429:
        raise HTTPError
    return BeautifulSoup(req.content, features="lxml")
