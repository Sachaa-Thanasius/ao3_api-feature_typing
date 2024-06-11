import re
import warnings
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Mapping, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from AO3.series import Series

from . import utils
from .chapters import Chapter
from .comments import Comment
from .requester import requester
from .threadable import threadable
from .users import User


if TYPE_CHECKING:
    from requests import Response

    from .session import GuestSession


FileType = Literal["AZW3", "EPUB", "HTML", "MOBI", "PDF"]


class Work:
    """
    AO3 work object
    """

    def __init__(
        self,
        workid: int,
        session: Optional[GuestSession] = None,
        load: bool = True,
        load_chapters: bool = True,
    ):
        """Creates a new AO3 work object

        Args:
            workid (int): AO3 work ID
            session (AO3.Session, optional): Used to access restricted works
            load (bool, optional): If true, the work is loaded on initialization. Defaults to True.
            load_chapters (bool, optional): If false, chapter text won't be parsed, and Work.load_chapters() will have
            to be called. Defaults to True.

        Raises:
            utils.InvalidIdError: Raised if the work wasn't found
        """

        self._session: Optional[GuestSession] = session
        self.chapters: list[Chapter] = []
        self.id = workid
        self._soup: Optional[BeautifulSoup] = None
        if load:
            self.reload(load_chapters)

    def __repr__(self) -> str:
        return f"<Work [{self.title or self.id}]>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, __class__) and other.id == self.id

    def __getstate__(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        for attr in self.__dict__:
            if isinstance((item := self.__dict__[attr]), BeautifulSoup):
                d[attr] = (item.encode(), True)
            else:
                d[attr] = (item, False)
        return d

    def __setstate__(self, d: Mapping[str, Any]) -> None:
        for attr in d:
            value, issoup = d[attr]
            self.__dict__[attr] = BeautifulSoup(value, "lxml") if issoup else value

    @threadable
    def reload(self, load_chapters: bool = True) -> None:
        """
        Loads information about this work.
        This function is threadable.

        Args:
            load_chapters (bool, optional): If false, chapter text won't be parsed, and Work.load_chapters() will have
            to be called. Defaults to True.
        """

        for attr in self.__class__.__dict__:
            if isinstance(getattr(self.__class__, attr), cached_property) and attr in self.__dict__:
                delattr(self, attr)

        self._soup = self.request(f"https://archiveofourown.org/works/{self.id}?view_adult=true&view_full_work=true")

        if (heading := self._soup.find("h2", {"class", "heading"})) and ("Error 404" in heading.text):
            msg = "Cannot find work"
            raise utils.InvalidIdError(msg)
        if load_chapters:
            self.load_chapters()

    def set_session(self, session: GuestSession) -> None:
        """Sets the session used to make requests for this work

        Args:
            session (AO3.Session/AO3.GuestSession): session object
        """

        self._session = session

    def load_chapters(self) -> None:
        """Loads chapter objects for each one of this work's chapters"""

        if self._soup:
            self.chapters = []
            chapters_div = self._soup.find(attrs={"id": "chapters"})
            if chapters_div is None:
                return
            assert isinstance(chapters_div, Tag)

            if self.nchapters > 1:
                for chap in chapters_div.find_all("div", attrs={"id", re.compile(r"chapter-\d*")}):
                    if not chap:
                        return
                    assert isinstance(chap, Tag)
                    temp_chap = chap.extract()
                    preface_group = temp_chap.find("div", attrs={"class": ("chapter", "preface", "group")})
                    if not preface_group:
                        continue
                    assert isinstance(preface_group, Tag)
                    title = preface_group.find("h3", attrs={"class": "title"})
                    if title is None:
                        continue
                    assert isinstance(title, Tag)
                    id_ = int(title.a["href"].split("/")[-1])
                    c = Chapter(id_, self, self._session, False)
                    c._soup = chap  # type: ignore
                    self.chapters.append(c)
            else:
                c = Chapter(None, self, self._session, False)
                c._soup = chapters_div  # type: ignore
                self.chapters.append(c)

    def get_images(self) -> Dict[int, Tuple[str, ...]]:
        """Gets all images from this work

        Raises:
            utils.UnloadedError: Raises this error if the work isn't loaded

        Returns:
            dict: key = chapter_n; value = chapter.get_images()
        """

        if not self.loaded:
            raise utils.UnloadedError("Work isn't loaded. Have you tried calling Work.reload()?")

        chapters: Dict[int, Tuple[str, ...]] = {}
        for chapter in self.chapters:
            images = chapter.get_images()
            if len(images) != 0:
                chapters[chapter.number] = images
        return chapters

    def download(self, filetype: FileType = "PDF") -> bytes:
        """Downloads this work

        Args:
            filetype (str, optional): Desired filetype. Defaults to "PDF".
            Known filetypes are: AZW3, EPUB, HTML, MOBI, PDF.

        Raises:
            utils.DownloadError: Raised if there was an error with the download
            utils.UnexpectedResponseError: Raised if the filetype is not available for download

        Returns:
            bytes: File content
        """

        if not self.loaded:
            raise utils.UnloadedError("Work isn't loaded. Have you tried calling Work.reload()?")
        assert self._soup

        download_btn = self._soup.find("li", {"class": "download"})
        for download_type in download_btn.find_all("li"):
            if download_type.a.get_text() == filetype.upper():
                url = f"https://archiveofourown.org/{download_type.a.attrs['href']}"
                req = self.get(url)
                if req.status_code == 429:
                    raise utils.HTTPError
                if not req.ok:
                    msg = "An error occurred while downloading the work"
                    raise utils.DownloadError(msg)
                return req.content
        msg = f"Filetype '{filetype}' is not available for download"
        raise utils.UnexpectedResponseError(msg)

    @threadable
    def download_to_file(self, filename: str, filetype: FileType = "PDF") -> None:
        """Downloads this work and saves it in the specified file.
        This function is threadable.

        Args:
            filename (str): Name of the resulting file
            filetype (str, optional): Desired filetype. Defaults to "PDF".
            Known filetypes are: AZW3, EPUB, HTML, MOBI, PDF.

        Raises:
            utils.DownloadError: Raised if there was an error with the download
            utils.UnexpectedResponseError: Raised if the filetype is not available for download
        """
        with Path(filename).open("wb") as file:
            file.write(self.download(filetype))

    @property
    def metadata(self) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        normal_fields = (
            "bookmarks",
            "categories",
            "nchapters",
            "characters",
            "complete",
            "comments",
            "expected_chapters",
            "fandoms",
            "hits",
            "kudos",
            "language",
            "rating",
            "relationships",
            "restricted",
            "status",
            "summary",
            "tags",
            "title",
            "warnings",
            "id",
            "words",
            "collections",
        )
        string_fields = (
            "date_edited",
            "date_published",
            "date_updated",
        )

        for field in string_fields:
            try:
                metadata[field] = str(getattr(self, field))
            except AttributeError:
                pass

        for field in normal_fields:
            try:
                metadata[field] = getattr(self, field)
            except AttributeError:
                pass

        try:
            metadata["authors"] = [author.username for author in self.authors]
        except AttributeError:
            pass
        try:
            metadata["series"] = [series.name for series in self.series]
        except AttributeError:
            pass
        try:
            metadata["chapter_titles"] = [chapter.title for chapter in self.chapters]
        except AttributeError:
            pass

        return metadata

    def get_comments(self, maximum: Optional[int] = None) -> List[Comment]:
        """Returns a list of all threads of comments in the work. This operation can take a very long time.
        Because of that, it is recomended that you set a maximum number of comments.
        Duration: ~ (0.13 * n_comments) seconds or 2.9 seconds per comment page

        Args:
            maximum (int, optional): Maximum number of comments to be returned. None -> No maximum

        Raises:
            ValueError: Invalid chapter number
            IndexError: Invalid chapter number
            utils.UnloadedError: Work isn't loaded

        Returns:
            list: List of comments
        """

        if not self.loaded:
            msg = "Work isn't loaded. Have you tried calling Work.reload()?"
            raise utils.UnloadedError(msg)

        url = f"https://archiveofourown.org/works/{self.id}?page=%d&show_comments=true&view_adult=true&view_full_work=true"
        soup = self.request(url % 1)

        pages = 0
        div = soup.find("div", {"id": "comments_placeholder"})
        ol = div.find("ol", {"class": "pagination actions"})
        if ol is None:
            pages = 1
        else:
            assert isinstance(ol, Tag)
            for li in reversed(ol.find_all("li")):
                if li.get_text().isdigit():
                    pages = int(li.get_text())
                    break

        comments: list[Comment] = []
        for page in range(pages):
            if page != 0:
                soup = self.request(url % (page + 1))
            ol = soup.find("ol", {"class": "thread"})
            for li in ol.find_all("li", {"role": "article"}, recursive=False):
                assert isinstance(li, Tag)
                if maximum is not None and len(comments) >= maximum:
                    return comments
                id_ = int(li.attrs["id"][8:])

                header = li.find("h4", {"class": ("heading", "byline")})
                author = (
                    None
                    if not (isinstance(header, Tag) and header.a)
                    else User(str(header.a.text), self._session, False)
                )

                text = li.blockquote.getText() if li.blockquote is not None else ""

                comment = Comment(id_, self, session=self._session, load=False)
                comment.authenticity_token = self.authenticity_token
                comment.author = author
                comment.text = text
                comment._thread = None  # type: ignore
                comments.append(comment)
        return comments

    @threadable
    def subscribe(self) -> None:
        """Subscribes to this work.
        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

        if self._session is None or not self._session.is_authed:
            raise utils.AuthError("You can only subscribe to a work using an authenticated session")

        utils.subscribe(self, "Work", self._session)

    @threadable
    def unsubscribe(self) -> None:
        """Unubscribes from this user.
        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

        if not self.is_subscribed:
            raise Exception("You are not subscribed to this work")
        if self._session is None or not self._session.is_authed:
            raise utils.AuthError("You can only unsubscribe from a work using an authenticated session")

        utils.subscribe(self, "Work", self._session, True, self._sub_id)

    @cached_property
    def text(self) -> str:
        """This work's text"""

        return "\n".join(chapter.text for chapter in self.chapters)

    @cached_property
    def authenticity_token(self) -> Optional[str]:
        """Token used to take actions that involve this work"""

        if not self.loaded:
            return None

        assert self._soup
        token = self._soup.find("meta", {"name": "csrf-token"})
        assert isinstance(token, Tag)
        return token.attrs["content"]

    @cached_property
    def is_subscribed(self) -> bool:
        """True if you're subscribed to this work"""

        if self._session is None or not self._session.is_authed:
            raise utils.AuthError("You can only get a user ID using an authenticated session")

        ul = self._soup.find("ul", {"class": "work navigation actions"})
        input_ = ul.find("li", {"class": "subscribe"}).find("input", {"name": "commit", "value": "Unsubscribe"})
        return input_ is not None

    @cached_property
    def _sub_id(self) -> int:
        """Returns the subscription ID. Used for unsubscribing"""

        if self._session is None or not self._session.is_authed:
            raise utils.AuthError("You can only get a user ID using an authenticated session")

        ul = self._soup.find("ul", {"class": "work navigation actions"})
        id_ = ul.find("li", {"class": "subscribe"}).form.attrs["action"].split("/")[-1]
        return int(id_)

    @threadable
    def leave_kudos(self) -> bool:
        """Leave a "kudos" in this work.
        This function is threadable.

        Raises:
            utils.UnexpectedResponseError: Unexpected response received
            utils.InvalidIdError: Invalid ID (work doesn't exist)
            utils.AuthError: Invalid session or authenticity token

        Returns:
            bool: True if successful, False if you already left kudos there
        """

        if self._session is None:
            raise utils.AuthError("Invalid session")
        return utils.kudos(self, self._session)

    @threadable
    def comment(self, comment_text: str, email: str = "", name: str = "", pseud: Optional[str] = None) -> Response:
        """Leaves a comment on this work.
        This function is threadable.

        Args:
            comment_text (str): Comment text
            email (str, optional): Email to add comment. Needed if not logged in.
            name (str, optional): Name to add comment under. Needed if not logged in.
            pseud (str, optional): Pseud to add the comment under. Defaults to default pseud.

        Raises:
            utils.UnloadedError: Couldn't load chapters
            utils.AuthError: Invalid session

        Returns:
            requests.models.Response: Response object
        """

        if not self.loaded:
            raise utils.UnloadedError("Work isn't loaded. Have you tried calling Work.reload()?")

        if self._session is None:
            raise utils.AuthError("Invalid session")

        return utils.comment(self, comment_text, self._session, True, email=email, name=name, pseud=pseud)

    @threadable
    def bookmark(
        self,
        notes: str = "",
        tags: Optional[List[str]] = None,
        collections: Optional[List[str]] = None,
        private: bool = False,
        recommend: bool = False,
        pseud: Optional[str] = None,
    ) -> None:
        """Bookmarks this work
        This function is threadable

        Args:
            notes (str, optional): Bookmark notes. Defaults to "".
            tags (list, optional): What tags to add. Defaults to None.
            collections (list, optional): What collections to add this bookmark to. Defaults to None.
            private (bool, optional): Whether this bookmark should be private. Defaults to False.
            recommend (bool, optional): Whether to recommend this bookmark. Defaults to False.
            pseud (str, optional): What pseud to add the bookmark under. Defaults to default pseud.

        Raises:
            utils.UnloadedError: Work isn't loaded
            utils.AuthError: Invalid session
        """

        if not self.loaded:
            raise utils.UnloadedError("Work isn't loaded. Have you tried calling Work.reload()?")

        if self._session is None:
            raise utils.AuthError("Invalid session")

        utils.bookmark(self, self._session, notes, tags, collections, private, recommend, pseud)

    @threadable
    def delete_bookmark(self) -> None:
        """Removes a bookmark from this work
        This function is threadable

        Raises:
            utils.UnloadedError: Work isn't loaded
            utils.AuthError: Invalid session
        """

        if not self.loaded:
            raise utils.UnloadedError("Work isn't loaded. Have you tried calling Work.reload()?")

        if self._session is None:
            raise utils.AuthError("Invalid session")

        if self._bookmarkid is None:
            raise utils.BookmarkError("You don't have a bookmark here")

        utils.delete_bookmark(self._bookmarkid, self._session, self.authenticity_token)

    @threadable
    def collect(self, collections: List[str]) -> None:
        """Invites/collects this work to a collection or collections
        This function is threadable

        Args:
            collections (list): What collections to add this work to. Defaults to None.

        Raises:
            utils.UnloadedError: Work isn't loaded
            utils.AuthError: Invalid session
        """

        if not self.loaded:
            raise utils.UnloadedError("Work isn't loaded. Have you tried calling Work.reload()?")

        if self._session is None:
            raise utils.AuthError("Invalid session")

        utils.collect(self, self._session, collections)

    @cached_property
    def _bookmarkid(self) -> Optional[int]:
        form_div = self._soup.find("div", {"id": "bookmark-form"})
        if form_div is None:
            return None
        assert isinstance(form_div, Tag)

        if form_div.form is None:
            return None
        assert isinstance(form_div.form, Tag)

        if "action" in form_div.form.attrs and (action := form_div.form.attrs["action"]).startswith("/bookmarks"):
            text = action.split("/")[-1]
            if text.isdigit():
                return int(text)
        return None

    @property
    def loaded(self) -> bool:
        """Returns True if this work has been loaded"""
        return self._soup is not None

    @property
    def oneshot(self) -> bool:
        """Returns True if this work has only one chapter"""
        return self.nchapters == 1

    @cached_property
    def series(self) -> List[Series]:
        """Returns the series this work belongs to"""

        from .series import Series

        dd = self._soup.find("dd", {"class": "series"})
        if dd is None:
            return []

        s = []
        for span in dd.find_all("span", {"class": "position"}):
            seriesid = int(span.a.attrs["href"].split("/")[-1])
            seriesname = span.a.getText()
            series = Series(seriesid, self._session, False)
            setattr(series, "name", seriesname)
            s.append(series)
        return s

    @cached_property
    def authors(self) -> List[User]:
        """Returns the list of the work's author

        Returns:
            list: list of authors
        """

        from .users import User

        authors = self._soup.find_all("h3", {"class": "byline heading"})
        if len(authors) == 0:
            return []
        formatted_authors = authors[0].text.replace("\n", "").split(", ")
        author_list = []
        if authors is not None:
            for author in formatted_authors:
                user = User(author, load=False)
                author_list.append(user)

        return author_list

    @cached_property
    def nchapters(self) -> int:
        """Returns the number of chapters of this work

        Returns:
            int: number of chapters
        """

        chapters = self._soup.find("dd", {"class": "chapters"})
        if chapters is not None:
            return int((chapters.string.split("/")[0]).replace(",", ""))
        return 0

    @cached_property
    def expected_chapters(self) -> Optional[int]:
        """Returns the number of expected chapters for this work, or None if
        the author hasn't provided an expected number

        Returns:
            int: number of chapters
        """
        chapters = self._soup.find("dd", {"class": "chapters"})
        if chapters is not None:
            n = (chapters.string.split("/")[-1]).replace(",", "")
            if n.isdigit():
                return int(n)
        return None

    @property
    def status(self) -> str:
        """Returns the status of this work

        Returns:
            str: work status
        """

        return "Completed" if self.nchapters == self.expected_chapters else "Work in Progress"

    @cached_property
    def hits(self) -> int:
        """Returns the number of hits this work has

        Returns:
            int: number of hits
        """

        hits = self._soup.find("dd", {"class": "hits"})
        if hits is not None:
            return int((hits.string).replace(",", ""))
        return 0

    @cached_property
    def kudos(self) -> int:
        """Returns the number of kudos this work has

        Returns:
            int: number of kudos
        """

        kudos = self._soup.find("dd", {"class": "kudos"})
        if kudos is not None:
            return int((kudos.string).replace(",", ""))
        return 0

    @cached_property
    def comments(self) -> int:
        """Returns the number of comments this work has

        Returns:
            int: number of comments
        """

        comments = self._soup.find("dd", {"class": "comments"})
        if comments is not None:
            return int((comments.string).replace(",", ""))
        return 0

    @cached_property
    def restricted(self) -> bool:
        """Whether this is a restricted work or not

        Returns:
            int: True if work is restricted
        """
        return self._soup.find("img", {"title": "Restricted"}) is not None

    @cached_property
    def words(self) -> int:
        """Returns the this work's word count

        Returns:
            int: number of words
        """

        words = self._soup.find("dd", {"class": "words"})
        if words is not None:
            return int((words.string).replace(",", ""))
        return 0

    @cached_property
    def language(self) -> str:
        """Returns this work's language

        Returns:
            str: Language
        """

        language = self._soup.find("dd", {"class": "language"})
        if language is not None:
            return language.string.strip()
        return "Unknown"

    @cached_property
    def bookmarks(self) -> int:
        """Returns the number of bookmarks this work has

        Returns:
            int: number of bookmarks
        """

        bookmarks = self._soup.find("dd", {"class": "bookmarks"})
        if bookmarks is not None:
            return int((bookmarks.string).replace(",", ""))
        return 0

    @cached_property
    def title(self) -> str:
        """Returns the title of this work

        Returns:
            str: work title
        """

        title = self._soup.find("div", {"class": "preface group"})
        if title is not None:
            return str(title.h2.text.strip())
        return ""

    @cached_property
    def date_published(self) -> datetime:
        """Returns the date this work was published

        Returns:
            datetime.date: publish date
        """

        dp = self._soup.find("dd", {"class": "published"}).string
        return datetime(*list(map(int, dp.split("-"))))

    @cached_property
    def date_edited(self) -> datetime:
        """Returns the date this work was last edited

        Returns:
            datetime.datetime: edit date
        """

        download = self._soup.find("li", {"class": "download"})
        if download is not None and download.ul is not None:
            timestamp = int(download.ul.a["href"].split("=")[-1])
            return datetime.fromtimestamp(timestamp)
        return datetime(self.date_published)

    @cached_property
    def date_updated(self) -> datetime:
        """Returns the date this work was last updated

        Returns:
            datetime.datetime: update date
        """
        update = self._soup.find("dd", {"class": "status"})
        if update is not None:
            split = update.string.split("-")
            return datetime(*list(map(int, split)))
        return self.date_published

    @cached_property
    def tags(self) -> List[str]:
        """Returns all the work's tags

        Returns:
            list: List of tags
        """

        html = self._soup.find("dd", {"class": "freeform tags"})
        tags: list[str] = []
        if html is not None:
            for tag in html.find_all("li"):
                tags.append(tag.a.string)
        return tags

    @cached_property
    def characters(self) -> List[str]:
        """Returns all the work's characters

        Returns:
            list: List of characters
        """

        html = self._soup.find("dd", {"class": "character tags"})
        characters: List[str] = []
        if html is not None:
            for character in html.find_all("li"):
                characters.append(character.a.string)
        return characters

    @cached_property
    def relationships(self) -> List[str]:
        """Returns all the work's relationships

        Returns:
            list: List of relationships
        """

        html = self._soup.find("dd", {"class": "relationship tags"})
        relationships: List[str] = []
        if html is not None:
            for relationship in html.find_all("li"):
                relationships.append(relationship.a.string)
        return relationships

    @cached_property
    def fandoms(self) -> List[str]:
        """Returns all the work's fandoms

        Returns:
            list: List of fandoms
        """

        html = self._soup.find("dd", {"class": "fandom tags"})
        fandoms: List[str] = []
        if html is not None:
            for fandom in html.find_all("li"):
                fandoms.append(fandom.a.string)
        return fandoms

    @cached_property
    def categories(self) -> List[str]:
        """Returns all the work's categories

        Returns:
            list: List of categories
        """

        html = self._soup.find("dd", {"class": "category tags"})
        categories: List[str] = []
        if html is not None:
            for category in html.find_all("li"):
                categories.append(category.a.string)
        return categories

    @cached_property
    def warnings(self) -> List[str]:
        """Returns all the work's warnings

        Returns:
            list: List of warnings
        """

        html = self._soup.find("dd", {"class": "warning tags"})
        warnings: List[str] = []
        if html is not None:
            for warning in html.find_all("li"):
                warnings.append(warning.a.string)
        return warnings

    @cached_property
    def rating(self) -> Optional[str]:
        """Returns this work's rating

        Returns:
            str: Rating
        """

        html = self._soup.find("dd", {"class": "rating tags"})
        if html is not None:
            rating = html.a.string
            return rating
        return None

    @cached_property
    def summary(self) -> str:
        """Returns this work's summary

        Returns:
            str: Summary
        """

        div = self._soup.find("div", {"class": "preface group"})
        if div is None:
            return ""
        html = div.find("blockquote", {"class": "userstuff"})
        if html is None:
            return ""
        return str(html.get_text())

    @cached_property
    def start_notes(self) -> str:
        """Text from this work's start notes"""
        notes = self._soup.find("div", {"class": "notes module"})
        if notes is None:
            return ""
        if not (p_notes := notes.find_all("p")):
            return ""
        return "\n".join(p.get_text().strip() for p in p_notes)

    @cached_property
    def end_notes(self) -> str:
        """Text from this work's end notes"""
        notes = self._soup.find("div", {"id": "work_endnotes"})
        if notes is None:
            return ""
        if not (p_notes := notes.find_all("p")):
            return ""
        return "\n".join(p.get_text().strip() for p in p_notes)

    @cached_property
    def url(self) -> str:
        """Returns the URL to this work

        Returns:
            str: work URL
        """

        return f"https://archiveofourown.org/works/{self.id}"

    @cached_property
    def complete(self) -> bool:
        """
        Return True if the work is complete

        Retuns:
            bool: True if a work is complete
        """

        chapterStatus = self._soup.find("dd", {"class": "chapters"}).string.split("/")
        return chapterStatus[0] == chapterStatus[1]

    @cached_property
    def collections(self) -> List[str]:
        """Returns all the collections the work belongs to

        Returns:
            list: List of collections
        """

        html = self._soup.find("dd", {"class": "collections"})
        collections: List[str] = []
        if html is not None:
            for collection in html.find_all("a"):
                collections.append(collection.get_text())
        return collections

    def get(self, *args: Any, **kwargs: Any) -> Response:
        """Request a web page and return a Response object"""

        if self._session is None:
            req = requester.request("get", *args, **kwargs)
        else:
            req = requester.request("get", *args, **kwargs, session=self._session.session)
        if req.status_code == 429:
            raise utils.HTTPError
        return req

    def request(self, url: str) -> BeautifulSoup:
        """Request a web page and return a BeautifulSoup object.

        Args:
            url (str): Url to request

        Returns:
            bs4.BeautifulSoup: BeautifulSoup object representing the requested page's html
        """

        req = self.get(url)
        if len(req.content) > 650000:
            warnings.warn("This work is very big and might take a very long time to load")
        return BeautifulSoup(req.content, "lxml")

    @staticmethod
    def str_format(string: str) -> str:
        """Formats a given string

        Args:
            string (str): String to format

        Returns:
            str: Formatted string
        """

        return string.replace(",", "")
