import pickle
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, NoReturn, Optional, Union
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .requester import requester


if TYPE_CHECKING:
    from typing_extensions import TypeAlias

    from requests import Response

    from .chapters import Chapter
    from .comments import Comment
    from .series import Series
    from .session import GuestSession, Session
    from .users import User
    from .works import Work

Bookmarkable: TypeAlias = Union[Work, Series]
Collectable: TypeAlias = Work
Commentable: TypeAlias = Union[Work, Chapter]
Kudoable: TypeAlias = Work
Subscribable: TypeAlias = Union[Work, Series, User]

# Made these globals lowercase.
_fandoms: Optional[List[str]] = None
_languages: Optional[List[str]] = None

AO3_AUTH_ERROR_URL = "https://archiveofourown.org/auth_error"
AO3_WORK_REGEX = re.compile(r"(?:https://|)(?:www\.|)archiveofourown\.org/works/(?P<ao3_id>\d+)")


class AO3Error(Exception):
    """Base exception for AO3."""

    def __init__(self, message: Optional[str] = None, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []


class LoginError(AO3Error):
    """Exception that's raised when an attempt to log in to AO3 fails."""

    def __init__(self, message: Optional[str] = None, errors: Optional[List[str]] = None):
        message = message or "Login was unsucessful (wrong username or password)"
        super().__init__(message, errors)


class UnloadedError(AO3Error):
    """Exception that's raised when the content of an AO3 object hasn't been loaded, but accessing it was attempted."""


class UnexpectedResponseError(AO3Error):
    """Exception that's raised when something 'unexpected' happens. Used liberally."""


class InvalidIdError(AO3Error):
    """Exception that's raised when an invalid AO3 object ID was passed in."""


class DownloadError(AO3Error):
    """Exception that's raised when downloading an AO3 work fails."""


class AuthError(AO3Error):
    """Exception that's raised when the authentication token for the AO3 session is invalid."""


class DuplicateCommentError(AO3Error):
    """Exception that's raised when attempting to post a comment that already exists."""


class PseudError(AO3Error):
    """Exception that's raised when a pseud's ID couldn't be found."""


class HTTPError(AO3Error):
    """Exception that's raised when being rate-limited."""

    def __init__(self, message: Optional[str] = None, errors: Optional[List[str]] = None):
        message = message or "We are being rate-limited. Try again in a while or reduce the number of requests."
        super().__init__(message, errors)


class BookmarkError(AO3Error):
    """Exception that's raised when attempting to create or access a bookmark fails."""


class CollectError(AO3Error):
    """Exception that's raised when attempting to invite a work to a collection fails."""


class Query:
    def __init__(self) -> None:
        self.fields: list[str] = []

    def add_field(self, text: str) -> None:
        self.fields.append(text)

    @property
    def string(self) -> str:
        return "&".join(self.fields)


class Constraint:
    """Represents a bounding box of a value"""

    def __init__(self, lowerbound: int = 0, upperbound: Optional[int] = None) -> None:
        """Creates a new Constraint object

        Args:
            lowerbound (int, optional): Constraint lowerbound. Defaults to 0.
            upperbound (int, optional): Constraint upperbound. Defaults to None.
        """

        self._lb = lowerbound
        self._ub = upperbound

    def __str__(self) -> str:
        if self._lb == 0:
            return f"<{self._ub}"
        if self._ub is None:
            return f">{self._lb}"
        if self._ub == self._lb:
            return str(self._lb)

        return f"{self._lb}-{self._ub}"

    @property
    def string(self) -> str:
        """Returns the string representation of this constraint

        Returns:
            str: string representation
        """
        return str(self)


def word_count(text: str) -> int:
    return len(tuple(word for word in re.split(r" |\n|\t", text) if bool(word)))


def set_rqtw(value: int) -> None:
    """Sets the requests per time window parameter for the AO3 requester"""
    requester.rqtw = value


def set_timew(value: int) -> None:
    """Sets the time window parameter for the AO3 requester"""
    requester.timew = value


def limit_requests(limit: bool = True) -> None:
    """Toggles request limiting"""
    value = 12 if limit else -1
    requester.rqtw = value


def load_fandoms() -> None:
    """Loads fandoms into memory

    Raises:
        FileNotFoundError: No resource was found
    """

    global _fandoms  # noqa: PLW0603

    fandom_path = Path(__file__).parent / "resources" / "fandoms"
    if not fandom_path.is_dir():
        msg = "No fandom resources have been downloaded. Try AO3.extra.download()"
        raise FileNotFoundError(msg)

    _fandoms = []  # noqa: PLW0603
    for file in fandom_path.iterdir():
        with file.open("rb") as f:
            _fandoms += pickle.load(f)  # noqa: S301


def load_languages() -> None:
    """Loads languages into memory

    Raises:
        FileNotFoundError: No resource was found
    """

    global _languages  # noqa: PLW0603

    language_path = Path(__file__).parent / "resources" / "languages"
    if not language_path.is_dir():
        msg = "No language resources have been downloaded. Try AO3.extra.download()"
        raise FileNotFoundError(msg)

    _languages = []  # noqa: PLW0603
    for file in language_path.iterdir():
        with file.open("rb") as f:
            _languages += pickle.load(f)  # noqa: S301


def get_languages() -> List[str]:
    """Returns all available languages"""
    return _languages[:] if _languages else []


def search_fandom(fandom_string: str) -> List[str]:
    """Searches for a fandom that matches the given string

    Args:
        fandom_string (str): query string

    Raises:
        UnloadedError: load_fandoms() wasn't called
        UnloadedError: No resources were downloaded

    Returns:
        list: All results matching 'fandom_string'
    """

    if _fandoms is None:
        msg = "Did you forget to call AO3.utils.load_fandoms()?"
        raise UnloadedError(msg)
    if not _fandoms:
        msg = "Did you forget to download the required resources with AO3.extra.download()?"
        raise UnloadedError(msg)
    results: list[str] = [fandom for fandom in _fandoms if fandom_string.lower() in fandom.lower()]
    return results


def workid_from_url(url: str) -> Optional[int]:
    """Get the workid from an archiveofourown.org website url

    Args:
        url (str): Work URL

    Returns:
        int: Work ID
    """
    result = AO3_WORK_REGEX.search(url)
    return int(result.group("ao3_id")) if result else None


def comment(
    commentable: Commentable,
    comment_text: str,
    session: GuestSession,
    fullwork: bool = False,
    commentid: Optional[Union[str, int]] = None,
    email: str = "",
    name: str = "",
    pseud: Optional[str] = None,
) -> Response:
    """Leaves a comment on a specific work

    Args:
        commentable (Work/Chapter): Chapter/Work object
        comment_text (str): Comment text (must have between 1 and 10000 characters)
        fullwork (bool): Should be True if the work has only one chapter or if the comment is to be posted on the full
        work.
        session (AO3.Session/AO3.GuestSession): Session object to request with.
        commentid (str/int): If specified, the comment is posted as a reply to this comment. Defaults to None.
        email (str): Email to post with. Only used if sess is None. Defaults to "".
        name (str): Name that will appear on the comment. Only used if sess is None. Defaults to "".
        pseud (str, optional): What pseud to add the comment under. Defaults to default pseud.

    Raises:
        utils.InvalidIdError: Invalid ID
        utils.UnexpectedResponseError: Unknown error
        utils.PseudError: Couldn't find a valid pseudonym to post under
        utils.DuplicateCommentError: The comment you're trying to post was already posted
        ValueError: Invalid name/email

    Returns:
        requests.models.Response: Response object
    """

    at: str = commentable.authenticity_token if commentable.authenticity_token else session.authenticity_token  # type: ignore # FIXME

    headers: Dict[str, Any] = {
        "x-requested-with": "XMLHttpRequest",
        "x-newrelic-id": "VQcCWV9RGwIJVFFRAw==",
        "x-csrf-token": at,
    }

    data: Dict[str, Any] = {"authenticity_token": at}
    if fullwork:
        data["work_id"] = str(commentable.id)
    else:
        data["chapter_id"] = str(commentable.id)
    if commentid is not None:
        data["comment_id"] = commentid

    if session.is_authed:
        # referer = f"https://archiveofourown.org/{'works' if fullwork else 'chapters'}/{commentable.id}"

        pseud_id = get_pseud_id(commentable, session, pseud)
        if pseud_id is None:
            msg = "Couldn't find your pseud's id"
            raise PseudError(msg)

        data.update({"comment[pseud_id]": pseud_id, "comment[comment_content]": comment_text})

    else:
        if email == "" or name == "":
            msg = "You need to specify both an email and a name!"
            raise ValueError(msg)

        data.update({"comment[email]": email, "comment[name]": name, "comment[comment_content]": comment_text})

    response = session.post("https://archiveofourown.org/comments.js", headers=headers, data=data)
    if response.status_code == 429:
        raise HTTPError

    if response.status_code == 404:
        if len(response.content) > 0:
            return response
        msg = f"Invalid {'work ID' if fullwork else 'chapter ID'}"
        raise InvalidIdError(msg)

    if response.status_code == 422:
        json_ = response.json()
        if "errors" in json_ and "auth_error" in json_["errors"]:
            msg = "Invalid authentication token. Try calling session.refresh_auth_token()"
            raise AuthError(msg)

        msg = f"Unexpected json received:\n{json_!s}"
        raise UnexpectedResponseError(msg)

    if response.status_code == 200:
        msg = "You have already left this comment here"
        raise DuplicateCommentError(msg)

    msg = f"Unexpected HTTP status code received ({response.status_code})"
    raise UnexpectedResponseError(msg)


def delete_comment(comment: Comment, session: Optional[Session] = None) -> None:
    """Deletes the specified comment

    Args:
        comment (AO3.Comment): Comment object
        session (AO3.Session): Session object

    Raises:
        PermissionError: You don't have permission to delete the comment
        utils.AuthError: Invalid auth token
        utils.UnexpectedResponseError: Unknown error
    """

    if session is None or not session.is_authed:
        msg = "You don't have permission to do this"
        raise PermissionError(msg)

    at: str = comment.authenticity_token if comment.authenticity_token is not None else session.authenticity_token  # type: ignore # FIXME

    data: Dict[str, Any] = {"authenticity_token": at, "_method": "delete"}

    req = session.post(f"https://archiveofourown.org/comments/{comment.id}", data=data)
    if req.status_code == 429:
        raise HTTPError

    soup = BeautifulSoup(req.content, "lxml")
    if soup.title and ("auth error" in soup.title.get_text().lower()):
        msg = "Invalid authentication token. Try calling session.refresh_auth_token()"
        raise AuthError(msg)

    main_div = soup.find("div", {"id": "main"})
    error = main_div.get_text() if main_div else ""
    if "you don't have permission" in error.lower():
        msg = "You don't have permission to do this"
        raise PermissionError(msg)


def kudos(work: Kudoable, session: GuestSession) -> bool:
    """Leave a 'kudos' in a specific work

    Args:
        work (Work): Work object

    Raises:
        utils.UnexpectedResponseError: Unexpected response received
        utils.InvalidIdError: Invalid ID (work doesn't exist)
        utils.AuthError: Invalid authenticity token

    Returns:
        bool: True if successful, False if you already left kudos there
    """

    at: str = work.authenticity_token if work.authenticity_token is not None else session.authenticity_token  # type: ignore # FIXME

    headers: Dict[str, Any] = {
        "x-csrf-token": at,
        "x-requested-with": "XMLHttpRequest",
        "referer": f"https://archiveofourown.org/work/{work.id}",
    }
    data: Dict[str, Any] = {"authenticity_token": at, "kudo[commentable_id]": work.id, "kudo[commentable_type]": "Work"}
    response = session.post("https://archiveofourown.org/kudos.js", headers=headers, data=data)
    if response.status_code == 429:
        raise HTTPError

    if response.status_code == 201:
        return True  # Success

    if response.status_code == 422:
        json_ = response.json()
        if "errors" in json_:
            if "auth_error" in json_["errors"]:
                msg = "Invalid authentication token. Try calling session.refresh_auth_token()"
                raise AuthError(msg)

            if "user_id" in json_["errors"] or "ip_address" in json_["errors"]:
                return False  # User has already left kudos

            if "no_commentable" in json_["errors"]:
                raise InvalidIdError
        msg = f"Unexpected json received:\n{json_}"
        raise UnexpectedResponseError(msg)
    msg = f"Unexpected HTTP status code received ({response.status_code})"
    raise UnexpectedResponseError(msg)


def subscribe(
    subscribable: Subscribable,
    worktype: str,
    session: Optional[GuestSession] = None,
    unsubscribe: bool = False,
    subid: Optional[Union[str, int]] = None,
) -> Optional[Response]:
    """Subscribes to a work. Be careful, you can subscribe to a work multiple times

    Args:
        subscribable (Work/Series/User): AO3 object
        worktype (str): Type of the work (Series/Work/User)
        session (AO3.Session): Session object
        unsubscribe (bool, optional): Unsubscribe instead of subscribing. Defaults to False.
        subid (str/int, optional): Subscription ID, used when unsubscribing. Defaults to None.

    Raises:
        AuthError: Invalid auth token
        AuthError: Invalid session
        InvalidIdError: Invalid ID / worktype
        InvalidIdError: Invalid subid
    """

    if session is None:
        session = subscribable._session
    if session is None or not session.is_authed:
        msg = "Invalid session"
        raise AuthError(msg)

    at: str = subscribable.authenticity_token if subscribable.authenticity_token else session.authenticity_token  # type: ignore # FIXME

    data: Dict[str, Any] = {
        "authenticity_token": at,
        "subscription[subscribable_id]": subscribable.id,
        "subscription[subscribable_type]": worktype.capitalize(),
    }

    url = f"https://archiveofourown.org/users/{session.username}/subscriptions"
    if unsubscribe:
        if subid is None:
            msg = "When unsubscribing, subid cannot be None"
            raise InvalidIdError(msg)
        url += f"/{subid}"
        data["_method"] = "delete"
    req: Response = session.session.post(url, data=data, allow_redirects=False)  # type: ignore # FIXME
    if unsubscribe:
        return req
    if req.status_code == 302 and req.headers["Location"] == AO3_AUTH_ERROR_URL:
        msg = "Invalid authentication token. Try calling session.refresh_auth_token()"
        raise AuthError(msg)

    msg = "Invalid ID / worktype"
    raise InvalidIdError(msg)


def bookmark(
    bookmarkable: Bookmarkable,
    session: Optional[GuestSession] = None,
    notes: str = "",
    tags: Optional[List[str]] = None,
    collections: Optional[List[str]] = None,
    private: bool = False,
    recommend: bool = False,
    pseud: Optional[str] = None,
) -> None:
    """Adds a bookmark to a work/series. Be careful, you can bookmark a work multiple times

    Args:
        bookmarkable (Work/Series): AO3 object
        session (AO3.Session): Session object
        notes (str, optional): Bookmark notes. Defaults to "".
        tags (list, optional): What tags to add. Defaults to None.
        collections (list, optional): What collections to add this bookmark to. Defaults to None.
        private (bool, optional): Whether this bookmark should be private. Defaults to False.
        recommend (bool, optional): Whether to recommend this bookmark. Defaults to False.
        pseud (str, optional): What pseud to add the bookmark under. Defaults to default pseud.
    """

    if session is None:
        session = bookmarkable._session
    if (session is None) or not session.is_authed:
        msg = "Invalid session"
        raise AuthError(msg)

    at: str = bookmarkable.authenticity_token if bookmarkable.authenticity_token else session.authenticity_token  # type: ignore # FIXME

    if tags is None:
        tags = []
    if collections is None:
        collections = []

    pseud_id = get_pseud_id(bookmarkable, session, pseud)
    if pseud_id is None:
        msg = "Couldn't find your pseud's id"
        raise PseudError(msg)

    data: Dict[str, Any] = {
        "authenticity_token": at,
        "bookmark[pseud_id]": pseud_id,
        "bookmark[tag_string]": ",".join(tags),
        "bookmark[collection_names]": ",".join(collections),
        "bookmark[private]": int(private),
        "bookmark[rec]": int(recommend),
        "commit": "Create",
    }

    if notes != "":
        data["bookmark[bookmarker_notes]"] = notes

    url = urljoin(bookmarkable.url + "/", "bookmarks")
    req = session.session.post(url, data=data, allow_redirects=False)
    handle_bookmark_errors(req)


def delete_bookmark(
    bookmarkid: int,
    session: Optional[GuestSession] = None,
    auth_token: Optional[str] = None,
) -> None:
    """Remove a bookmark from the work/series

    Args:
        bookmarkid (Work/Series): AO3 object
        session (AO3.Session): Session object
        auth_token (str, optional): Authenticity token. Defaults to None.
    """
    if (session is None) or not session.is_authed:
        msg = "Invalid session"
        raise AuthError(msg)

    data: Dict[str, Any] = {
        "authenticity_token": auth_token if auth_token else session.authenticity_token,
        "_method": "delete",
    }

    url = f"https://archiveofourown.org/bookmarks/{bookmarkid}"
    req = session.session.post(url, data=data, allow_redirects=False)
    handle_bookmark_errors(req)


def handle_bookmark_errors(request: Response) -> NoReturn:
    if request.status_code == 302:
        if request.headers["Location"] == AO3_AUTH_ERROR_URL:
            msg = "Invalid authentication token. Try calling session.refresh_auth_token()"
            raise AuthError(msg)
    elif request.status_code == 200:
        soup = BeautifulSoup(request.content, "lxml")
        error_div = soup.find("div", {"id": "error", "class": "error"})
        if error_div is None:
            msg = "An unknown error occurred"
            raise UnexpectedResponseError(msg)

        assert isinstance(error_div, Tag)
        errors = [item.get_text() for item in error_div.findAll("li")]
        if len(errors) == 0:
            msg = "An unknown error occurred"
            raise BookmarkError(msg)
        raise BookmarkError("Error(s) creating bookmark:" + " ".join(errors))

    msg = f"Unexpected HTTP status code received ({request.status_code})"
    raise UnexpectedResponseError(msg)


def get_pseud_id(
    ao3object: Union[Work, Series, Chapter],
    session: Optional[GuestSession] = None,
    specified_pseud: Optional[str] = None,
) -> Optional[str]:
    if session is None:
        session = ao3object._session
    if session is None or not session.is_authed:
        raise AuthError("Invalid session")

    soup: BeautifulSoup = session.request(ao3object.url)  # type: ignore # FIXME
    pseud = soup.find("input", {"name": re.compile(r".+\[pseud_id\]")})
    if pseud is None:
        pseud = soup.find("select", {"name": re.compile(r".+\[pseud_id\]")})
        if pseud is None:
            return None

        assert isinstance(pseud, Tag)
        pseud_id = None
        if specified_pseud:
            for option in pseud.find_all("option"):
                assert isinstance(option, Tag)
                if option.string == specified_pseud:
                    pseud_id = option.attrs["value"]
                    break
        else:
            for option in pseud.find_all("option"):
                assert isinstance(option, Tag)
                if "selected" in option.attrs and option.attrs["selected"] == "selected":
                    pseud_id = option.attrs["value"]
                    break
    else:
        assert isinstance(pseud, Tag)
        pseud_id = pseud.attrs["value"]
    return pseud_id


def collect(
    collectable: Collectable,
    session: Optional[GuestSession] = None,
    collections: Optional[List[str]] = None,
) -> None:
    """Invites a work to a collection. Be careful, you can collect a work multiple times

    Args:
        work (Work): Work object
        session (AO3.Session): Session object
        collections (list, optional): What collections to add this work to. Defaults to None.
    """

    if session is None:
        session = collectable._session
    if (session is None) or not session.is_authed:
        msg = "Invalid session"
        raise AuthError(msg)

    at: str = collectable.authenticity_token if collectable.authenticity_token else session.authenticity_token  # type: ignore # FIXME

    if collections is None:
        collections = []

    data: Dict[str, Any] = {"authenticity_token": at, "collection_names": ",".join(collections), "commit": "Add"}

    url = urljoin(collectable.url + "/", "collection_items")
    req: Response = session.session.post(url, data=data, allow_redirects=True)  # type: ignore # FIXME

    if req.status_code == 302:
        if req.headers["Location"] == AO3_AUTH_ERROR_URL:
            msg = "Invalid authentication token. Try calling session.refresh_auth_token()"
            raise AuthError(msg)
    elif req.status_code == 200:
        soup = BeautifulSoup(req.content, "lxml")
        notice_div = soup.find("div", {"class": "notice"})
        error_div = soup.find("div", {"class": "error"})

        if error_div is None and notice_div is None:
            raise UnexpectedResponseError("An unknown error occurred")

        if isinstance(error_div, Tag):
            errors = [item.get_text() for item in error_div.find_all("ul")]

            if len(errors) == 0:
                msg = "An unknown error occurred"
                raise CollectError(msg)

            raise CollectError("We couldn't add your submission to the following collection(s): " + " ".join(errors))

    msg = f"Unexpected HTTP status code received ({req.status_code})"
    raise UnexpectedResponseError(msg)
