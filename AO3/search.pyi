from typing import Final

from bs4 import BeautifulSoup

from .session import GuestSession
from .threadable import threadable
from .utils import Constraint
from .works import Work

DEFAULT: Final[str]
BEST_MATCH: Final[str]
AUTHOR: Final[str]
TITLE: Final[str]
DATE_POSTED: Final[str]
DATE_UPDATED: Final[str]
WORD_COUNT: Final[str]
RATING: Final[str]
HITS: Final[str]
BOOKMARKS: Final[str]
COMMENTS: Final[str]
KUDOS: Final[str]
DESCENDING: Final[str]
ASCENDING: Final[str]

class Search:
    any_field: str | None
    title: str
    author: str
    single_chapter: bool
    word_count: Constraint | None
    language: str
    fandoms: str
    rating: int | None
    hits: Constraint | None
    kudos: Constraint | None
    crossovers: bool | None
    bookmarks: Constraint | None
    excluded_tags: str
    comments: Constraint | None
    completion_status: bool | None
    page: int
    sort_column: str
    sort_direction: str
    revised_at: str
    characters: str
    relationships: str
    tags: str
    session: GuestSession | None = None
    results: list[Work] | None
    pages: int
    total_results: int
    def __init__(
        self,
        any_field: str | None = ...,
        title: str = ...,
        author: str = ...,
        single_chapter: bool = ...,
        word_count: Constraint | None = ...,
        language: str = ...,
        fandoms: str = ...,
        rating: int | None = ...,
        hits: Constraint | None = ...,
        kudos: Constraint | None = ...,
        crossovers: bool | None = ...,
        bookmarks: Constraint | None = ...,
        excluded_tags: str = "",
        comments: Constraint | None = ...,
        completion_status: bool | None = ...,
        page: int = ...,
        sort_column: str = ...,
        sort_direction: str = ...,
        revised_at: str = ...,
        characters: str = ...,
        relationships: str = ...,
        tags: str = "",
        session: GuestSession | None = ...,
    ) -> None: ...
    @threadable
    def update(self) -> None: ...

def search(
    any_field: str | None = ...,
    title: str = ...,
    author: str = ...,
    single_chapter: bool = ...,
    word_count: Constraint | None = ...,
    language: str = ...,
    fandoms: str = ...,
    rating: int | None = ...,
    hits: Constraint | None = ...,
    kudos: Constraint | None = ...,
    crossovers: bool | None = ...,
    bookmarks: Constraint | None = ...,
    excluded_tags: str = "",
    comments: Constraint | None = ...,
    completion_status: bool | None = ...,
    page: int = ...,
    sort_column: str = ...,
    sort_direction: str = ...,
    revised_at: str = ...,
    session: GuestSession | None = ...,
    characters: str = ...,
    relationships: str = ...,
    tags: str = ...,
) -> BeautifulSoup: ...
