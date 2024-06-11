from functools import cached_property
from typing import TYPE_CHECKING, Any, Generator, List, Optional, TypeVar, Union

from bs4 import BeautifulSoup, Tag

from . import utils
from .requester import requester
from .threadable import threadable
from .users import User


if TYPE_CHECKING:
    from typing_extensions import Self

    from requests import Response

    from .chapters import Chapter
    from .session import GuestSession
    from .works import Work

CommentT = TypeVar("CommentT", bound="Comment")

class Comment:
    """
    AO3 comment object
    """

    def __init__(
        self,
        comment_id: Union[int, str],
        parent: Optional[Union[Work, Chapter]] = None,
        parent_comment: Optional[Self] = None,
        session: Optional[GuestSession] = None,
        load: bool = True,
    ) -> None:
        """Creates a new AO3 comment object

        Args:
            comment_id (int/str): Comment ID
            parent (Work/Chapter, optional): Parent object (where the comment is posted). Defaults to None.
            parent_comment (Comment, optional): Parent comment. Defaults to None.
            session (Session/GuestSession, optional): Session object
            load (boolean, optional):  If true, the comment is loaded on initialization. Defaults to True.
        """

        self.id = comment_id
        self.parent = parent
        self.parent_comment = parent_comment
        self.authenticity_token: Optional[str] = None
        self._thread: Optional[List[Self]] = None
        self._session = session
        self.__soup: Optional[BeautifulSoup] = None
        if load:
            self.reload()

    def __repr__(self) -> str:
        return f"<Comment [{self.id}] on [{self.parent}]>"

    @property
    def _soup(self) -> Optional[BeautifulSoup]:
        if self.__soup is None:
            if self.parent_comment is None:
                return None
            return self.parent_comment._soup
        return self.__soup

    @property
    def first_parent_comment(self) -> Self:
        if self.parent_comment is None:
            return self
        return self.parent_comment.first_parent_comment

    @property
    def fullwork(self) -> Optional[bool]:
        from .works import Work

        if self.parent is None:
            return None
        return isinstance(self.parent, Work)

    @cached_property
    def author(self) -> Optional[User]:
        """Comment author"""
        li = self._soup.find("li", {"id": f"comment_{self.id}"})
        header = li.find("h4", {"class": ("heading", "byline")})
        return None if header is None else User(str(header.a.text), self._session, False)

    @cached_property
    def text(self) -> str:
        """Comment text"""
        li = self._soup.find("li", {"id": f"comment_{self.id}"})
        return li.blockquote.get_text() if isinstance(li.blockquote, Tag) else ""

    def get_thread(self) -> Optional[List[Self]]:
        """Returns all the replies to this comment, and all subsequent replies recursively.
        Also loads any parent comments this comment might have.

        Raises:
            utils.InvalidIdError: The specified comment_id was invalid

        Returns:
            list: Thread
        """

        if self._thread is not None:
            return self._thread

        if self._soup is None:
            self.reload()
        assert self._soup

        nav = self._soup.find("ul", {"id": f"navigation_for_comment_{self.id}"})
        for li in nav.find_all("li"):
            assert isinstance(li, Tag)
            if li.get_text() == "\nParent Thread\n":
                id_ = int(li.a["href"].split("/")[-1])
                parent = Comment(id_, session=self._session)
                for comment in parent.get_thread_iterator():
                    if comment.id == self.id:
                        index = comment.parent_comment._thread.index(comment)
                        comment.parent_comment._thread.pop(index)
                        comment.parent_comment._thread.insert(index, self)
                        self._thread = comment._thread
                        self.parent_comment = comment.parent_comment
                        del comment
                        return self._thread

        thread = self._soup.find("ol", {"class": "thread"})
        if thread is None:
            self._thread = []
            return self._thread
        assert isinstance(thread, Tag)

        self._get_thread(None, thread)

        if self._thread is None:
            self._thread = []
        return self._thread

    def _get_thread(self, parent: Optional[Self], soup: Tag) -> None:
        comments = soup.find_all("li", recursive=False)
        list_comm: List[Self] = [self] if parent is None else []
        for comment in comments:
            if "role" in comment.attrs:
                id_ = int(comment.attrs["id"][8:])
                comm = Comment(id_, self.parent, session=self._session, load=False)
                comm.authenticity_token = self.authenticity_token
                comm._thread = []
                if parent is not None:
                    comm.parent_comment = parent
                    text = comment.blockquote.get_text() if comment.blockquote is not None else ""
                    author = User(comment.a.get_text(), load=False) if comment.a is not None else None
                    comm.text = text
                    comm.author = author
                    list_comm.append(comm)
                else:
                    comm.parent_comment = self
                    text = comment.blockquote.get_text() if comment.blockquote is not None else ""
                    author = User(comment.a.get_text(), load=False) if comment.a is not None else None
                    list_comm[0].text = text
                    list_comm[0].author = author
            else:
                self._get_thread(list_comm[-1], comment.ol)
        if parent is not None:
            parent._thread = list_comm

    def get_thread_iterator(self) -> Generator[Self, None, None]:
        """Returns a generator that allows you to iterate through the entire thread

        Returns:
            generator: The generator object
        """

        return threadIterator(self)

    @threadable
    def reply(self, comment_text: str, email: str = "", name: str = "") -> Response:
        """Replies to a comment.
        This function is threadable.

        Args:
            comment_text (str): Comment text
            email (str, optional): Email. Defaults to "".
            name (str, optional): Name. Defaults to "".

        Raises:
            utils.InvalidIdError: Invalid ID
            utils.UnexpectedResponseError: Unknown error
            utils.PseudoError: Couldn't find a valid pseudonym to post under
            utils.DuplicateCommentError: The comment you're trying to post was already posted
            ValueError: Invalid name/email
            ValueError: self.parent cannot be None

        Returns:
            requests.models.Response: Response object
        """

        if self.parent is None:
            raise ValueError("self.parent cannot be 'None'")
        return utils.comment(self.parent, comment_text, self._session, self.fullwork, self.id, email, name)

    @threadable
    def reload(self) -> None:
        """Loads all comment properties
        This function is threadable.
        """

        for attr in self.__class__.__dict__:
            if isinstance(getattr(self.__class__, attr), cached_property) and attr in self.__dict__:
                delattr(self, attr)

        req = self.get(f"https://archiveofourown.org/comments/{self.id}")
        self.__soup = BeautifulSoup(req.content, features="lxml")

        token = self.__soup.find("meta", {"name": "csrf-token"})
        self.authenticity_token = token.attrs["content"]

        self._thread = None

        li = self._soup.find("li", {"id": f"comment_{self.id}"})

        reply_link = li.find("li", {"id": f"add_comment_reply_link_{self.id}"})

        if self.parent is None and isinstance(reply_link, Tag):
            fields = [field.split("=") for field in reply_link.a["href"].split("?")[-1].split("&")]
            for key, value in fields:
                if key == "chapter_id":
                    self.parent = int(value)
                    break
        self.parent_comment = None

    @threadable
    def delete(self) -> None:
        """Deletes this comment.
        This function is threadable.

        Raises:
            PermissionError: You don't have permission to delete the comment
            utils.AuthError: Invalid auth token
            utils.UnexpectedResponseError: Unknown error
        """

        utils.delete_comment(self, self._session)

    def get(self, *args: Any, **kwargs: Any) -> Response:
        """Request a web page and return a Response object"""

        if self._session is None:
            req = requester.request("get", *args, **kwargs)
        else:
            req = requester.request("get", *args, **kwargs, session=self._session.session)
        if req.status_code == 429:
            raise utils.HTTPError
        return req


def threadIterator(comment: CommentT) -> Generator[CommentT, None, None]:
    if (thread := comment.get_thread()) is None or len(thread) == 0:
        yield comment
    else:
        for c in thread:
            yield c
            for sub in threadIterator(c):
                if c != sub:
                    yield sub
