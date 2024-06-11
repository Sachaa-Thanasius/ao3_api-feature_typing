from functools import cached_property
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

from bs4 import BeautifulSoup, NavigableString, Tag

from . import utils
from .comments import Comment
from .requester import requester
from .threadable import threadable


if TYPE_CHECKING:
    from requests import Response

    from .session import GuestSession
    from .works import Work


class Chapter:
    """
    AO3 chapter object
    """

    def __init__(
        self,
        chapterid: Optional[int],
        work: Optional[Work],
        session: Optional[GuestSession] = None,
        load: bool = True,
    ) -> None:
        self._session = session
        self._work = work
        self.id = chapterid
        self._soup: Optional[BeautifulSoup] = None
        if load:
            self.reload()

    def __repr__(self) -> str:
        if self.id is None:
            return f"Chapter [ONESHOT] from [{self.work}]"
        try:
            return f"<Chapter [{self.title} ({self.number})] from [{self.work}]>"
        except Exception:
            return f"<Chapter [{self.id}] from [{self.work}]>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, __class__) and other.id == self.id

    def __getstate__(self) -> Dict[str, Any]:
        return {
            attr: (val.encode() if (is_soup := isinstance(val, BeautifulSoup)) else val, is_soup)
            for attr, val in self.__dict__.items()
        }

    def __setstate__(self, d: Mapping[str, Any]) -> None:
        self.__dict__.update(
            {attr: (BeautifulSoup(value, "lxml") if issoup else value) for attr, (value, issoup) in d.items()},
        )

    def set_session(self, session: GuestSession) -> None:
        """Sets the session used to make requests for this chapter

        Args:
            session (AO3.Session/AO3.GuestSession): session object
        """

        self._session = session

    @threadable
    def reload(self) -> None:
        """
        Loads information about this chapter.
        This function is threadable.
        """
        from .works import Work

        for attr in self.__class__.__dict__:
            if isinstance(getattr(self.__class__, attr), cached_property) and attr in self.__dict__:
                delattr(self, attr)

        if self.work is None:
            soup = self.request(f"https://archiveofourown.org/chapters/{self.id}?view_adult=true")
            workid = soup.find("li", {"class": "chapter entire"})
            if workid is None:
                raise utils.InvalidIdError("Cannot find work")
            self._work = Work(utils.workid_from_url(workid.a["href"]))
        else:
            self.work.reload()

        for chapter in self.work.chapters:
            if chapter == self:
                self._soup = chapter._soup

    @threadable
    def comment(
        self,
        comment_text: str,
        email: str = "",
        name: str = "",
        pseud: Optional[str] = None,
    ) -> Optional[Response]:
        """Leaves a comment on this chapter.
        This function is threadable.

        Args:
            comment_text (str): Comment text

        Raises:
            utils.UnloadedError: Couldn't load chapters
            utils.AuthError: Invalid session

        Returns:
            requests.models.Response: Response object
        """

        if self.id is None:
            return self._work.comment(comment_text, email, name, pseud)

        if not self.loaded:
            raise utils.UnloadedError("Chapter isn't loaded. Have you tried calling Chapter.reload()?")

        if self._session is None:
            raise utils.AuthError("Invalid session")

        if self.id is not None:
            return utils.comment(self, comment_text, self._session, False, email=email, name=name, pseud=pseud)
        return None

    def get_comments(self, maximum: Optional[int] = None) -> List[Comment]:
        """Returns a list of all threads of comments in the chapter. This operation can take a very long time.
        Because of that, it is recomended that you set a maximum number of comments.
        Duration: ~ (0.13 * n_comments) seconds or 2.9 seconds per comment page

        Args:
            maximum (int, optional): Maximum number of comments to be returned. None -> No maximum

        Raises:
            ValueError: Invalid chapter number
            IndexError: Invalid chapter number
            utils.UnloadedError: Chapter isn't loaded

        Returns:
            list: List of comments
        """
        from .users import User

        if self.id is None:
            return self._work.get_comments(maximum=maximum)

        if not self.loaded:
            raise utils.UnloadedError("Chapter isn't loaded. Have you tried calling Chapter.reload()?")

        url = f"https://archiveofourown.org/chapters/{self.id}?page=%d&show_comments=true&view_adult=true"
        soup = self.request(url % 1)

        pages = 0
        div = soup.find("div", {"id": "comments_placeholder"})
        ol = div.find("ol", {"class": "pagination actions"})
        if not isinstance(ol, Tag):
            pages = 1
        else:
            pages = next((int(li.get_text()) for li in ol.find_all() if li.get_text().isdigit()), 1)

        comments: List[Comment] = []
        for page in range(pages):
            if page != 0:
                soup = self.request(url % (page + 1))
            ol = soup.find("ol", {"class": "thread"})
            for li in ol.findAll("li", {"role": "article"}, recursive=False):
                if maximum is not None and len(comments) >= maximum:
                    return comments
                id_ = int(li.attrs["id"][8:])

                header = li.find("h4", {"class": ("heading", "byline")})
                author = None if header is None else User(str(header.a.text), self._session, False)

                text = li.blockquote.getText() if li.blockquote is not None else ""

                comment = Comment(id_, self, session=self._session, load=False)
                comment.authenticity_token = self.authenticity_token
                comment.author = author
                comment.text = text
                comment._thread = None  # type: ignore
                comments.append(comment)
        return comments

    def get_images(self) -> Tuple[Tuple[str, int], ...]:
        """Gets all images from this work

        Raises:
            utils.UnloadedError: Raises this error if the chapter isn't loaded

        Returns:
            tuple: Pairs of image urls and the paragraph number
        """

        div = self._soup.find("div", {"class": "userstuff"})

        if isinstance(div, Tag):
            return tuple(
                (img.attrs["src"], line)
                for line, p in enumerate(div.find_all("p"), 1)
                for img in p.find_all("img")
                if "src" in img.attrs
            )

        raise utils.UnloadedError("Chapter isn't loaded")

    @property
    def loaded(self) -> bool:
        """Returns True if this chapter has been loaded"""
        return self._soup is not None

    @property
    def authenticity_token(self) -> Optional[str]:
        """Token used to take actions that involve this work"""
        try:
            return self.work.authenticity_token  # type: ignore # Guarded by except clause.
        except AttributeError:
            return None

    @property
    def work(self) -> Optional[Work]:
        """Work this chapter is a part of"""
        return self._work

    @cached_property
    def text(self) -> str:
        """This chapter's text"""
        text = ""
        div = self._soup.find("div", {"role": "article"}) if self.id is not None else self._soup
        for p in div.find_all(("p", "center")):
            text += p.getText().replace("\n", "") + "\n"
            if isinstance(p.next_sibling, NavigableString):
                text += str(p.next_sibling)
        return text

    @cached_property
    def title(self) -> str:
        """This chapter's title"""
        if self.id is None:
            return self.work.title
        preface_group = self._soup.find("div", {"class": ("chapter", "preface", "group")})
        if preface_group is None:
            return str(self.number)
        title = preface_group.find("h3", {"class": "title"})
        if title is None:
            return str(self.number)
        return tuple(title.strings)[-1].strip()[2:]

    @cached_property
    def number(self) -> int:
        """This chapter's number"""
        if self.id is None:
            return 1
        return int(self._soup["id"].split("-")[-1])

    @cached_property
    def words(self) -> int:
        """Number of words from this chapter"""
        return utils.word_count(self.text)

    @cached_property
    def summary(self) -> str:
        """Text from this chapter's summary"""
        notes = self._soup.find("div", {"id": "summary"})
        if notes is None:
            return ""
        assert isinstance(notes, Tag)
        return "\n".join(p.get_text() for p in ps) if (ps := notes.find_all()) else ""

    @cached_property
    def start_notes(self) -> str:
        """Text from this chapter's start notes"""
        notes = self._soup.find("div", {"id": "notes"})
        if notes is None:
            return ""
        assert isinstance(notes, Tag)
        return "\n".join(p.getText().strip() for p in ps) if (ps := notes.find_all("p")) else ""

    @cached_property
    def end_notes(self) -> str:
        """Text from this chapter's end notes"""
        notes = self._soup.find("div", {"id": f"chapter_{self.number}_endnotes"})
        if notes is None:
            return ""
        assert isinstance(notes, Tag)
        return "\n".join(p.getText() for p in ps) if (ps := notes.find_all("p")) else ""

    @cached_property
    def url(self) -> str:
        """Returns the URL to this chapter

        Returns:
            str: chapter URL
        """

        return f"https://archiveofourown.org/works/{self._work.id}/chapters/{self.id}"

    def request(self, url: str) -> BeautifulSoup:
        """Request a web page and return a BeautifulSoup object.

        Args:
            url (str): Url to request

        Returns:
            bs4.BeautifulSoup: BeautifulSoup object representing the requested page's html
        """

        req = self.get(url)
        return BeautifulSoup(req.content, "lxml")

    def get(self, *args: Any, **kwargs: Any) -> Response:
        """Request a web page and return a Response object"""

        if self._session is None:
            req = requester.request("get", *args, **kwargs)
        else:
            req = requester.request("get", *args, **kwargs, session=self._session.session)
        if req.status_code == 429:
            raise utils.HTTPError
        return req
