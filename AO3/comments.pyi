from collections.abc import Generator
from functools import cached_property
from typing import TypeVar
from typing_extensions import Self

from bs4 import BeautifulSoup, Tag
from requests import Response

from .chapters import Chapter
from .session import GuestSession
from .threadable import threadable
from .users import User
from .works import Work

_CommentT = TypeVar("_CommentT", bound="Comment")

class Comment:
    id: int | str
    parent: Work | Chapter | None
    parent_comment: Self | None
    authenticity_token: str | None
    _thread: list[Self] | None
    _session: GuestSession | None
    __soup: BeautifulSoup | None
    def __init__(
        self,
        comment_id: int | str,
        parent: Work | Chapter | None = ...,
        parent_comment: Self | None = ...,
        session: GuestSession | None = ...,
        load: bool = ...,
    ) -> None: ...
    def __repr__(self) -> str: ...
    @property
    def _soup(self) -> BeautifulSoup | None: ...
    @property
    def first_parent_comment(self) -> Self: ...
    @property
    def fullwork(self) -> bool | None: ...
    @cached_property
    def author(self) -> User | None: ...
    @cached_property
    def text(self) -> str: ...
    def get_thread(self) -> list[Self] | None: ...
    def _get_thread(self, parent: Self | None, soup: Tag) -> None: ...
    def get_thread_iterator(self) -> Generator[Self, None, None]: ...
    @threadable
    def reply(self, comment_text: str, email: str = ..., name: str = ...) -> Response: ...
    @threadable
    def reload(self) -> None: ...
    @threadable
    def delete(self) -> None: ...

def threadIterator(comment: _CommentT) -> Generator[_CommentT, None, None]: ...
