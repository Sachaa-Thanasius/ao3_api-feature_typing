import datetime
import re
import time
from functools import cached_property
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple, Union

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from . import threadable, utils
from .requester import requester
from .series import Series
from .users import User
from .works import Chapter, Work


if TYPE_CHECKING:
    from threading import Thread

Subscribable = Union[Work, Series, User]

class GuestSession:
    """
    AO3 guest session object
    """

    def __init__(self) -> None:
        self.is_authed = False
        self.authenticity_token: Optional[str] = None
        self.username = ""
        self.session = requests.Session()

    def __del__(self) -> None:
        self.session.close()

    @property
    def user(self) -> User:
        return User(self.username, self, False)

    @threadable.threadable
    def comment(
        self,
        commentable: Union[Work, Chapter],
        comment_text: str,
        oneshot: bool = False,
        commentid: Optional[Union[str, int]] = None,
    ) -> requests.Response:
        """Leaves a comment on a specific work.
        This function is threadable.

        Args:
            commentable (Work/Chapter): Commentable object
            comment_text (str): Comment text (must have between 1 and 10000 characters)
            oneshot (bool): Should be True if the work has only one chapter. In this case, chapterid becomes workid
            commentid (str/int): If specified, the comment is posted as a reply to this one. Defaults to None.

        Raises:
            utils.InvalidIdError: Invalid ID
            utils.UnexpectedResponseError: Unknown error
            utils.PseudoError: Couldn't find a valid pseudonym to post under
            utils.DuplicateCommentError: The comment you're trying to post was already posted
            ValueError: Invalid name/email

        Returns:
            requests.models.Response: Response object
        """

        return utils.comment(commentable, comment_text, self, oneshot, commentid)

    @threadable.threadable
    def kudos(self, work: Work) -> bool:
        """Leave a 'kudos' in a specific work.
        This function is threadable.

        Args:
            work (Work): ID of the work

        Raises:
            utils.UnexpectedResponseError: Unexpected response received
            utils.InvalidIdError: Invalid ID (work doesn't exist)

        Returns:
            bool: True if successful, False if you already left kudos there
        """

        return utils.kudos(work, self)

    @threadable.threadable
    def refresh_auth_token(self) -> None:
        """Refreshes the authenticity token.
        This function is threadable.

        Raises:
            utils.UnexpectedResponseError: Couldn't refresh the token
        """

        # For some reason, the auth token in the root path only works if you're
        # unauthenticated. To get around that, we check if this is an authed
        # session and, if so, get the token from the profile page.

        if self.is_authed:
            req = self.session.get(f"https://archiveofourown.org/users/{self.username}")
        else:
            req = self.session.get("https://archiveofourown.org")

        if req.status_code == 429:
            raise utils.HTTPError

        soup = BeautifulSoup(req.content, "lxml")
        self.authenticity_token = self.extract_authenticity_token(soup)

    @staticmethod
    def extract_authenticity_token(soup: Tag) -> str:
        token = soup.find("input", {"name": "authenticity_token"})
        if isinstance(token, NavigableString) or token is None:
            msg = "Couldn't refresh token"
            raise utils.UnexpectedResponseError(msg)
        return token.attrs["value"]

    def get(self, *args: Any, **kwargs: Any) -> requests.Response:
        """Request a web page and return a Response object"""
        if not self.session:
            req = requester.request("get", *args, **kwargs)
        else:
            req = requester.request("get", *args, **kwargs, session=self.session)
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

    def post(self, *args: Any, **kwargs: Any) -> requests.Response:
        """Make a post request with the current session

        Returns:
            requests.Request
        """

        req = self.session.post(*args, **kwargs)
        if req.status_code == 429:
            raise utils.HTTPError
        return req


class Session(GuestSession):
    """
    AO3 session object
    """

    def __init__(self, username: str, password: str) -> None:
        """Creates a new AO3 session object

        Args:
            username (str): AO3 username
            password (str): AO3 password

        Raises:
            utils.LoginError: Login was unsucessful (wrong username or password)
        """

        super().__init__()
        self.is_authed = True
        self.username = username
        self.url = f"https://archiveofourown.org/users/{self.username}"

        self.session = requests.Session()

        soup = self.request("https://archiveofourown.org/users/login")
        self.authenticity_token = self.extract_authenticity_token(soup)
        payload = {"user[login]": username, "user[password]": password, "authenticity_token": self.authenticity_token}
        post = self.post("https://archiveofourown.org/users/login", params=payload, allow_redirects=False)
        if post.status_code != 302:
            msg = "Invalid username or password"
            raise utils.LoginError(msg)

        self._subscriptions_url = "https://archiveofourown.org/users/{0}/subscriptions?page={1:d}"
        self._bookmarks_url = "https://archiveofourown.org/users/{0}/bookmarks?page={1:d}"
        self._history_url = "https://archiveofourown.org/users/{0}/readings?page={1:d}"

        self._bookmarks = None
        self._subscriptions: Optional[list[Union[Work, Series, User]]] = None
        self._history = None

    def __getstate__(self) -> Dict[str, Tuple[Any, bool]]:
        d: Dict[str, Tuple[Any, bool]] = {}
        for attr in self.__dict__:
            if isinstance((item := self.__dict__[attr]), BeautifulSoup):
                d[attr] = (item.encode(), True)
            else:
                d[attr] = (item, False)
        return d

    def __setstate__(self, d: Mapping[str, Tuple[Any, bool]]):
        for attr in d:
            value, issoup = d[attr]
            self.__dict__[attr] = BeautifulSoup(value, "lxml") if issoup else value

    def clear_cache(self) -> None:
        for attr in self.__class__.__dict__:
            if isinstance(getattr(self.__class__, attr), cached_property) and attr in self.__dict__:
                delattr(self, attr)
        self._bookmarks = None
        self._subscriptions = None

    @cached_property
    def _subscription_pages(self) -> int:
        url = self._subscriptions_url.format(self.username, 1)
        soup = self.request(url)
        pages = soup.find("ol", {"title": "pagination"})
        if pages is None:
            return 1
        n = 1
        assert isinstance(pages, Tag)
        for li in pages.findAll("li"):
            text: str = li.getText()
            if text.isdigit():
                n = int(text)
        return n

    def get_work_subscriptions(self, use_threading: bool = False) -> List[Work]:
        """
        Get subscribed works. Loads them if they haven't been previously

        Returns:
            list: List of work subscriptions
        """

        subs = self.get_subscriptions(use_threading)
        return [obj for obj in subs if isinstance(obj, Work)]

    def get_series_subscriptions(self, use_threading: bool = False) -> List[Series]:
        """
        Get subscribed series. Loads them if they haven't been previously

        Returns:
            list: List of series subscriptions
        """

        subs = self.get_subscriptions(use_threading)
        return [obj for obj in subs if isinstance(obj, Series)]

    def get_user_subscriptions(self, use_threading: bool = False) -> List[User]:
        """
        Get subscribed users. Loads them if they haven't been previously

        Returns:
            list: List of users subscriptions
        """

        subs = self.get_subscriptions(use_threading)
        return [obj for obj in subs if isinstance(obj, User)]

    def get_subscriptions(self, use_threading: bool = False) -> List[Subscribable]:
        """
        Get user's subscriptions. Loads them if they haven't been previously

        Returns:
            list: List of subscriptions
        """

        if self._subscriptions is None:
            if use_threading:
                self.load_subscriptions_threaded()
            else:
                self._subscriptions: list[Subscribable] = []
                for page in range(self._subscription_pages):
                    self._load_subscriptions(page=page + 1)
        return self._subscriptions

    @threadable.threadable
    def load_subscriptions_threaded(self) -> None:
        """
        Get subscribed works using threads.
        This function is threadable.
        """

        threads: list[Thread] = []
        self._subscriptions: list[Union[Work, Series, User]] = []
        for page in range(self._subscription_pages):
            threads.append(self._load_subscriptions(page=page + 1, threaded=True)) # Fix
        for thread in threads:
            thread.join()

    @threadable.threadable
    def _load_subscriptions(self, page: int = 1) -> None:
        url = self._subscriptions_url.format(self.username, page)
        soup = self.request(url)
        subscriptions = soup.find("dl", {"class": "subscription index group"})
        assert isinstance(subscriptions, Tag)
        for sub in subscriptions.find_all("dt"):
            type_ = "work"
            user = None
            series = None
            workid = None
            workname = None
            authors: list[User] = []
            for a in sub.find_all("a"):
                if "rel" in a.attrs:
                    if "author" in a["rel"]:
                        authors.append(User(str(a.string), load=False))
                elif a["href"].startswith("/works"):
                    workname = str(a.string)
                    workid = utils.workid_from_url(a["href"])
                elif a["href"].startswith("/users"):
                    type_ = "user"
                    user = User(str(a.string), load=False)
                else:
                    type_ = "series"
                    workname = str(a.string)
                    series = int(a["href"].split("/")[-1])
            if type_ == "work":
                new = Work(workid, load=False)
                setattr(new, "title", workname)
                setattr(new, "authors", authors)
                self._subscriptions.append(new)
            elif type_ == "user":
                self._subscriptions.append(user)
            elif type_ == "series":
                new = Series(series, load=False)
                setattr(new, "name", workname)
                setattr(new, "authors", authors)
                self._subscriptions.append(new)

    @cached_property
    def _history_pages(self) -> int:
        url = self._history_url.format(self.username, 1)
        soup = self.request(url)
        pages = soup.find("ol", {"title": "pagination"})
        if pages is None:
            return 1
        n = 1
        assert isinstance(pages, Tag)
        for li in pages.findAll("li"):
            text: str = li.getText()
            if text.isdigit():
                n = int(text)
        return n

    def get_history(
        self,
        hist_sleep: int = 3,
        start_page: int = 0,
        max_pages: Optional[int] = None,
        timeout_sleep: int = 60,
    ):
        """
        Get history works. Loads them if they haven't been previously.

        takes two arguments the first hist_sleep is an int and is a sleep to run between pages of history to load to
        avoid hitting the rate limiter, the second is an int of the maximum number of pages of history to load, by
        default this is None so loads them all.

        Arguments:
            hist_sleep (int to sleep between requests)
            start_page (int for page to start on, zero-indexed)
            max_pages  (int for page to end on, zero-indexed)
            timeout_sleep (int, if set will attempt to recovery from http errors, likely timeouts, if set to None will
            just attempt to load)

        Returns:
            list: List of tuples (Work, number-of-visits, datetime-last-visited)
        """

        if self._history is None:
            self._history = []
            for page in range(start_page, self._history_pages):
                # If we are attempting to recover from errors then
                # catch and loop, otherwise just call and go
                if not timeout_sleep:
                    self._load_history(page=page + 1)

                else:
                    loaded = False
                    while loaded is False:
                        try:
                            self._load_history(page=page + 1)
                            # print(f"Read history page {page+1}")
                            loaded = True

                        except utils.HTTPError:
                            # print(f"History being rate limited, sleeping for {timeout_sleep} seconds")
                            time.sleep(timeout_sleep)

                # Check for maximum history page load
                if max_pages is not None and page >= max_pages:
                    return self._history

                # Again attempt to avoid rate limiter, sleep for a few
                # seconds between page requests.
                if hist_sleep is not None and hist_sleep > 0:
                    time.sleep(hist_sleep)

        return self._history

    def _load_history(self, page: int = 1):
        url = self._history_url.format(self.username, page)
        soup = self.request(url)
        history = soup.find("ol", {"class": "reading work index group"})
        assert isinstance(history, Tag)
        for item in history.findAll("li", {"role": "article"}):
            # authors = []
            workname = None
            workid = None
            for a in item.h4.find_all("a"):
                if a.attrs["href"].startswith("/works"):
                    workname = str(a.string)
                    workid = utils.workid_from_url(a["href"])

            visited_date = None
            visited_num = 1
            for viewed in item.find_all("h4", {"class": "viewed heading"}):
                data_string = str(viewed)
                date_str = re.search("<span>Last visited:</span> (\d{2} .+ \d{4})", data_string)
                if date_str is not None:
                    raw_date = date_str.group(1)
                    date_time_obj = datetime.datetime.strptime(date_str.group(1), "%d %b %Y")
                    visited_date = date_time_obj

                visited_str = re.search("Visited (\d+) times", data_string)
                if visited_str is not None:
                    visited_num = int(visited_str.group(1))

            if workname != None and workid != None:
                new = Work(workid, load=False)
                setattr(new, "title", workname)
                # setattr(new, "authors", authors)
                hist_item = [new, visited_num, visited_date]
                # print(hist_item)
                if new not in self._history:
                    self._history.append(hist_item)

    @cached_property
    def _bookmark_pages(self) -> int:
        url = self._bookmarks_url.format(self.username, 1)
        soup = self.request(url)
        pages = soup.find("ol", {"title": "pagination"})
        if pages is None:
            return 1
        n = 1
        assert isinstance(pages, Tag)
        for li in pages.findAll("li"):
            text: str = li.getText()
            if text.isdigit():
                n = int(text)
        return n

    def get_bookmarks(self, use_threading: bool = False):
        """
        Get bookmarked works. Loads them if they haven't been previously

        Returns:
            list: List of tuples (workid, workname, authors)
        """

        if self._bookmarks is None:
            if use_threading:
                self.load_bookmarks_threaded()
            else:
                self._bookmarks = []
                for page in range(self._bookmark_pages):
                    self._load_bookmarks(page=page + 1)
        return self._bookmarks

    @threadable.threadable
    def load_bookmarks_threaded(self) -> None:
        """
        Get bookmarked works using threads.
        This function is threadable.
        """

        threads: list[Thread] = []
        self._bookmarks = []
        for page in range(self._bookmark_pages):
            threads.append(self._load_bookmarks(page=page + 1, threaded=True))
        for thread in threads:
            thread.join()

    @threadable.threadable
    def _load_bookmarks(self, page: int = 1) -> None:
        url = self._bookmarks_url.format(self.username, page)
        soup = self.request(url)
        bookmarks = soup.find("ol", {"class": "bookmark index group"})
        assert isinstance(bookmarks, Tag)
        for bookm in bookmarks.find_all("li", {"class": ["bookmark", "index", "group"]}):
            authors = []
            recommended = False
            workid = -1
            if bookm.h4 is not None:
                for a in bookm.h4.find_all("a"):
                    assert isinstance(a, Tag)
                    if "rel" in a.attrs:
                        if "author" in a["rel"]:
                            authors.append(User(str(a.string), load=False))
                    elif a.attrs["href"].startswith("/works"):
                        workname = str(a.string)
                        workid = utils.workid_from_url(a["href"])

                # Get whether the bookmark is recommended
                for span in bookm.p.find_all("span"):
                    if "title" in span.attrs and span["title"] == "Rec":
                        recommended = True

                if workid != -1:
                    new = Work(workid, load=False)
                    new.title = workname
                    new.authors = authors
                    setattr(new, "recommended", recommended)
                    if new not in self._bookmarks:
                        self._bookmarks.append(new)

    @cached_property
    def bookmarks(self) -> int:
        """Get the number of your bookmarks.
        Must be logged in to use.

        Returns:
            int: Number of bookmarks
        """

        url = self._bookmarks_url.format(self.username, 1)
        soup = self.request(url)
        div = soup.find("div", {"class": "bookmarks-index dashboard filtered region"})
        assert isinstance(div, Tag)
        h2 = div.h2.text.split()
        return int(h2[4].replace(",", ""))

    def get_statistics(self, year: Optional[int] = None) -> Dict[str, int]:
        actual_year = "All+Years" if year is None else str(year)
        url = f"https://archiveofourown.org/users/{self.username}/stats?year={actual_year}"
        soup = self.request(url)
        stats: Dict[str, int] = {}
        dt = soup.find("dl", {"class": "statistics meta group"})
        if isinstance(dt, Tag):
            for field in dt.findAll("dt"):
                name: str = field.getText()[:-1].lower().replace(" ", "_")
                if field.next_sibling is not None and field.next_sibling.next_sibling is not None:
                    value: str = field.next_sibling.next_sibling.getText().replace(",", "")
                    if value.isdigit():
                        stats[name] = int(value)

        return stats

    @staticmethod
    def str_format(string: str) -> str:
        """Formats a given string

        Args:
            string (str): String to format

        Returns:
            str: Formatted string
        """

        return string.replace(",", "")

    def get_marked_for_later(self, sleep=1, timeout_sleep=60):
        """
        Gets every marked for later work

        Arguments:
            sleep (int): The time to wait between page requests
            timeout_sleep (int): The time to wait after the rate limit is hit

        Returns:
            works (list): All marked for later works
        """
        pageRaw = (
            self.request(f"https://archiveofourown.org/users/{self.username}/readings?page=1&show=to-read")
            .find("ol", {"class": "pagination actions"})
            .find_all("li")
        )
        maxPage = int(pageRaw[len(pageRaw) - 2].text)
        works = []
        for page in range(maxPage):
            grabbed = False
            while grabbed == False:
                try:
                    workPage = self.request(
                        f"https://archiveofourown.org/users/{self.username}/readings?page={page+1}&show=to-read"
                    )
                    worksRaw = workPage.find_all("li", {"role": "article"})
                    for work in worksRaw:
                        try:
                            workId = int(work.h4.a.get("href").split("/")[2])
                            works.append(Work(workId, session=self, load=False))
                        except AttributeError:
                            pass
                    grabbed = True
                except utils.HTTPError:
                    time.sleep(timeout_sleep)
            time.sleep(sleep)
        return works
