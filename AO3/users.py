from functools import cached_property
from threading import Thread
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from . import utils
from .common import get_work_from_banner
from .requester import requester
from .threadable import threadable


if TYPE_CHECKING:
    from requests import Response

    from .session import GuestSession
    from .works import Work


class User:
    """
    AO3 user object
    """

    def __init__(self, username: str, session: Optional[GuestSession] = None, load: bool = True) -> None:
        """Creates a new AO3 user object

        Args:
            username (str): AO3 username
            session (AO3.Session, optional): Used to access additional info
            load (bool, optional): If true, the user is loaded on initialization. Defaults to True.
        """

        self.username = username
        self._session = session
        self._soup_works: Optional[BeautifulSoup] = None
        self._soup_profile: Optional[BeautifulSoup] = None
        self._soup_bookmarks: Optional[BeautifulSoup] = None
        self._works: Optional[List[Work]] = None
        self._bookmarks: Optional[List[Work]] = None
        self._authenticity_token: Optional[str] = None
        if load:
            self.reload()

    def __repr__(self) -> str:
        return f"<User [{self.username}]>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, __class__) and other.username == self.username

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
        """Sets the session used to make requests for this work

        Args:
            session (AO3.Session/AO3.GuestSession): session object
        """

        self._session = session

    @threadable
    def reload(self) -> None:
        """
        Loads information about this user.
        This function is threadable.
        """

        for attr in self.__class__.__dict__:
            if isinstance(getattr(self.__class__, attr), cached_property) and attr in self.__dict__:
                delattr(self, attr)
        """
        # Potential replacement for parts of this function.
        @threadable
        def req_x(username: str, attr: str, endpoint: str) -> None:
            setattr(self, attr, self.request(f"https://archiveofourown.org/users/{username}{endpoint}"))
            token = getattr(self, attr).find("meta", {"name": "csrf-token"})
            assert isinstance(token, Tag)
            self._authenticity_token = token.attrs["content"]

        soups_endpoints = [("_soup_works", "/works"), ("_soup_profile", "/profile"), ("_soup_bookmarks", "/bookmarks")]
        rs = [
            req_x(username=self.username, attr=attr, endpoint=endpoint, threaded=True)
            for attr, endpoint in soups_endpoints
        ]
        for r in rs:
            r.join()
        """

        @threadable
        def req_works(username: str) -> None:
            self._soup_works = self.request(f"https://archiveofourown.org/users/{username}/works")
            token = self._soup_works.find("meta", {"name": "csrf-token"})
            assert isinstance(token, Tag)
            self._authenticity_token = token.attrs["content"]

        @threadable
        def req_profile(username: str) -> None:
            self._soup_profile = self.request(f"https://archiveofourown.org/users/{username}/profile")
            token = self._soup_profile.find("meta", {"name": "csrf-token"})
            assert isinstance(token, Tag)
            self._authenticity_token = token.attrs["content"]

        @threadable
        def req_bookmarks(username: str) -> None:
            self._soup_bookmarks = self.request(f"https://archiveofourown.org/users/{username}/bookmarks")
            token = self._soup_bookmarks.find("meta", {"name": "csrf-token"})
            assert isinstance(token, Tag)
            self._authenticity_token = token.attrs["content"]

        rs = [
            req_works(self.username, threaded=True),
            req_profile(self.username, threaded=True),
            req_bookmarks(self.username, threaded=True),
        ]
        for r in rs:
            r.join()

        self._works = None
        self._bookmarks = None

    def get_avatar(self) -> Tuple[str, bytes]:
        """Returns a tuple containing the name of the file and its data

        Returns:
            tuple: (name: str, img: bytes)
        """

        icon = self._soup_profile.find("p", {"class": "icon"})
        src = icon.img.attrs["src"]
        name = src.split("/")[-1].split("?")[0]
        img = self.get(src).content
        return name, img

    @threadable
    def subscribe(self) -> None:
        """Subscribes to this user.
        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

        if self._session is None or not self._session.is_authed:
            raise utils.AuthError("You can only subscribe to a user using an authenticated session")

        utils.subscribe(self, "User", self._session)

    @threadable
    def unsubscribe(self) -> None:
        """Unubscribes from this user.
        This function is threadable.

        Raises:
            utils.AuthError: Invalid session
        """

        if not self.is_subscribed:
            raise Exception("You are not subscribed to this user")
        if self._session is None or not self._session.is_authed:
            raise utils.AuthError("You can only unsubscribe from a user using an authenticated session")

        utils.subscribe(self, "User", self._session, True, self._sub_id)

    @property
    def id(self) -> Optional[int]:
        id_ = self._soup_profile.find("input", {"id": "subscription_subscribable_id"})
        return int(id_.attrs["value"]) if isinstance(id_, Tag) else None

    @cached_property
    def is_subscribed(self) -> bool:
        """True if you're subscribed to this user"""

        if self._session is None or not self._session.is_authed:
            raise utils.AuthError("You can only get a user ID using an authenticated session")

        header = self._soup_profile.find("div", {"class": "primary header module"})
        input_ = header.find("input", {"name": "commit", "value": "Unsubscribe"})
        return input_ is not None

    @property
    def loaded(self) -> bool:
        """Returns True if this user has been loaded"""
        return self._soup_profile is not None

    @property
    def authenticity_token(self) -> Optional[str]:
        return self._authenticity_token

    # @cached_property
    # def authenticity_token(self):
    #     """Token used to take actions that involve this user"""
    #     if not self.loaded:
    #         return None
    #     token = self._soup_profile.find("meta", {"name": "csrf-token"})
    #     return token["content"]

    @cached_property
    def user_id(self) -> int:
        if self._session is None or not self._session.is_authed:
            raise utils.AuthError("You can only get a user ID using an authenticated session")

        header = self._soup_profile.find("div", {"class": "primary header module"})
        input_ = header.find("input", {"name": "subscription[subscribable_id]"})
        if input_ is None:
            raise utils.UnexpectedResponseError("Couldn't fetch user ID")
        assert isinstance(input_, Tag)
        return int(input_.attrs["value"])

    @cached_property
    def _sub_id(self) -> int:
        """Returns the subscription ID. Used for unsubscribing"""

        if not self.is_subscribed:
            raise Exception("You are not subscribed to this user")

        header = self._soup_profile.find("div", {"class": "primary header module"})
        id_ = header.form.attrs["action"].split("/")[-1]
        return int(id_)

    @cached_property
    def works(self) -> int:
        """Returns the number of works authored by this user

        Returns:
            int: Number of works
        """

        div = self._soup_works.find("div", {"class": "works-index dashboard filtered region"})
        h2 = div.h2.text.split()
        return int(h2[4].replace(",", ""))

    @cached_property
    def _works_pages(self) -> int:
        pages = self._soup_works.find("ol", {"title": "pagination"})
        if pages is None:
            return 1
        assert isinstance(pages, Tag)

        n = 1
        for li in pages.find_all("li"):
            text = li.get_text()
            if text.isdigit():
                n = int(text)
        return n

    def get_works(self, use_threading: bool = False) -> List[Work]:
        """
        Get works authored by this user.

        Returns:
            list: List of works
        """

        if self._works is None:
            self._works = []
            if use_threading:
                self.load_works_threaded()
            else:
                self._works = []
                for page in range(self._works_pages):
                    self._load_works(page=page + 1)
        return self._works

    @threadable
    def load_works_threaded(self) -> None:
        """
        Get the user's works using threads.
        This function is threadable.
        """

        threads: list[Thread] = []
        for page in range(self._works_pages):
            threads.append(self._load_works(page=page + 1, threaded=True))
        for thread in threads:
            thread.join()

    @threadable
    def _load_works(self, page: int = 1) -> None:
        if self._works is None:
            self._works = []
        self._soup_works = self.request(f"https://archiveofourown.org/users/{self.username}/works?page={page}")

        ol = self._soup_works.find("ol", {"class": "work index group"})

        for work in ol.find_all("li", {"role": "article"}):
            assert isinstance(work, Tag)
            if work.h4 is None:
                continue
            self._works.append(get_work_from_banner(work))

    @cached_property
    def bookmarks(self) -> int:
        """Returns the number of works user has bookmarked

        Returns:
            int: Number of bookmarks
        """

        div = self._soup_bookmarks.find("div", {"class": "bookmarks-index dashboard filtered region"})
        h2 = div.h2.text.split()
        return int(h2[4].replace(",", ""))

    @cached_property
    def _bookmarks_pages(self) -> int:
        pages = self._soup_bookmarks.find("ol", {"title": "pagination"})
        if pages is None:
            return 1
        assert isinstance(pages, Tag)

        n = 1
        for li in pages.find_all("li"):
            text = li.getText()
            if text.isdigit():
                n = int(text)
        return n

    def get_bookmarks(self, use_threading: bool = False) -> List[Work]:
        """
        Get this user's bookmarked works. Loads them if they haven't been previously

        Returns:
            list: List of works
        """

        if self._bookmarks is None:
            self._bookmarks = []
            if use_threading:
                self.load_bookmarks_threaded()
            else:
                self._bookmarks = []
                for page in range(self._bookmarks_pages):
                    self._load_bookmarks(page=page + 1)
        return self._bookmarks

    @threadable
    def load_bookmarks_threaded(self) -> None:
        """
        Get the user's bookmarks using threads.
        This function is threadable.
        """

        threads: list[Thread] = []
        for page in range(self._bookmarks_pages):
            threads.append(self._load_bookmarks(page=page + 1, threaded=True))
        for thread in threads:
            thread.join()

    @threadable
    def _load_bookmarks(self, page: int = 1) -> None:
        if self._bookmarks is None:
            self._bookmarks = []

        self._soup_bookmarks = self.request(f"https://archiveofourown.org/users/{self.username}/bookmarks?page={page}")

        ol = self._soup_bookmarks.find("ol", {"class": "bookmark index group"})

        for work in ol.find_all("li", {"role": "article"}):
            assert isinstance(work, Tag)
            if work.h4 is None:
                continue
            self._bookmarks.append(get_work_from_banner(work))

    @cached_property
    def bio(self) -> str:
        """Returns the user's bio

        Returns:
            str: User's bio
        """

        div = self._soup_profile.find("div", {"class": "bio module"})
        if div is None:
            return ""
        assert isinstance(div, Tag)
        blockquote = div.find("blockquote", {"class": "userstuff"})
        return blockquote.get_text() if blockquote is not None else ""

    @cached_property
    def url(self) -> str:
        """Returns the URL to the user's profile

        Returns:
            str: user profile URL
        """

        return "https://archiveofourown.org/users/%s" % self.username

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

    @property
    def work_pages(self) -> int:
        """
        Returns how many pages of works a user has

        Returns:
            int: Amount of pages
        """
        return self._works_pages
