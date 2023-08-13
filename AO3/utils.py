import os
import pickle
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .requester import requester


if TYPE_CHECKING:
    from .chapters import Chapter
    from .comments import Comment
    from .series import Series
    from .session import GuestSession, Session
    from .works import Work


_FANDOMS: Optional[List[str]] = None
_LANGUAGES: Optional[List[str]] = None

AO3_AUTH_ERROR_URL = "https://archiveofourown.org/auth_error"
AO3_WORK_REGEX = re.compile(r"(?:https://|)(?:www\.|)archiveofourown\.org/works/(?P<ao3_id>\d+)")


class AO3Error(Exception):
    """Base exception for AO3."""

    def __init__(self, message: Optional[str] = None, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []


class LoginError(AO3Error):
    """Exception that's raised when an attempt to log in to AO3 fails."""


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

    def __init__(self, lowerbound: int = 0, upperbound: Optional[int] = None):
        """Creates a new Constraint object

        Args:
            lowerbound (int, optional): Constraint lowerbound. Defaults to 0.
            upperbound (int, optional): Constraint upperbound. Defaults to None.
        """

        self._lb = lowerbound
        self._ub = upperbound

    @property
    def string(self) -> str:
        """Returns the string representation of this constraint

        Returns:
            str: string representation
        """

        if self._lb == 0:
            return f"<{self._ub}"
        if self._ub is None:
            return f">{self._lb}"
        if self._ub == self._lb:
            return str(self._lb)

        return f"{self._lb}-{self._ub}"

    def __str__(self):
        return self.string


def word_count(text: str) -> int:
    return len(tuple(filter(lambda w: w != "", re.split(" |\n|\t", text))))


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

    global _FANDOMS

    fandom_path = os.path.join(os.path.dirname(__file__), "resources", "fandoms")
    if not os.path.isdir(fandom_path):
        raise FileNotFoundError("No fandom resources have been downloaded. Try AO3.extra.download()")
    files = os.listdir(fandom_path)
    _FANDOMS = []
    for file in files:
        with open(os.path.join(fandom_path, file), "rb") as f:
            _FANDOMS += pickle.load(f)


def load_languages() -> None:
    """Loads languages into memory

    Raises:
        FileNotFoundError: No resource was found
    """

    global _LANGUAGES

    language_path = os.path.join(os.path.dirname(__file__), "resources", "languages")
    if not os.path.isdir(language_path):
        raise FileNotFoundError("No language resources have been downloaded. Try AO3.extra.download()")
    files = os.listdir(language_path)
    _LANGUAGES = []
    for file in files:
        with open(os.path.join(language_path, file), "rb") as f:
            _LANGUAGES += pickle.load(f)


def get_languages():
    """Returns all available languages"""
    return _LANGUAGES[:]


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

    if _FANDOMS is None:
        msg = "Did you forget to call AO3.utils.load_fandoms()?"
        raise UnloadedError(msg)
    if not _FANDOMS:
        msg = "Did you forget to download the required resources with AO3.extra.download()?"
        raise UnloadedError(msg)
    results: list[str] = []
    for fandom in _FANDOMS:
        if fandom_string.lower() in fandom.lower():
            results.append(fandom)
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
    commentable: Union[Work, Chapter],
    comment_text: str,
    session: GuestSession,
    fullwork: bool = False,
    commentid: Optional[Union[str, int]] = None,
    email: str = "",
    name: str = "",
    pseud: Optional[str] = None,
):
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

    at = commentable.authenticity_token if commentable.authenticity_token is not None else session.authenticity_token

    headers: Dict[str, Any] = {
        "x-requested-with": "XMLHttpRequest",
        "x-newrelic-id": "VQcCWV9RGwIJVFFRAw==",
        "x-csrf-token": at,
    }

    data: Dict[str, Any] = {}
    if fullwork:
        data["work_id"] = str(commentable.id)
    else:
        data["chapter_id"] = str(commentable.id)
    if commentid is not None:
        data["comment_id"] = commentid

    if session.is_authed:
        referer = f"https://archiveofourown.org/{'works' if fullwork else 'chapters'}/{commentable.id}"

        pseud_id = get_pseud_id(commentable, session, pseud)
        if pseud_id is None:
            msg = "Couldn't find your pseud's id"
            raise PseudError(msg)

        data.update(
            {
                "authenticity_token": at,
                "comment[pseud_id]": pseud_id,
                "comment[comment_content]": comment_text,
            },
        )

    else:
        if email == "" or name == "":
            msg = "You need to specify both an email and a name!"
            raise ValueError(msg)

        data.update(
            {
                "authenticity_token": at,
                "comment[email]": email,
                "comment[name]": name,
                "comment[comment_content]": comment_text,
            },
        )

    response = session.post("https://archiveofourown.org/comments.js", headers=headers, data=data)
    if response.status_code == 429:
        raise HTTPError

    if response.status_code == 404:
        if len(response.content) > 0:
            return response
        msg = f"Invalid {'work ID' if fullwork else 'chapter ID'}"
        raise InvalidIdError(msg)

    if response.status_code == 422:
        json = response.json()
        if "errors" in json and "auth_error" in json["errors"]:
            msg = "Invalid authentication token. Try calling session.refresh_auth_token()"
            raise AuthError(msg)

        msg = f"Unexpected json received:\n{json!s}"
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

    at = comment.authenticity_token if comment.authenticity_token is not None else session.authenticity_token

    data: Dict[str, Any] = {"authenticity_token": at, "_method": "delete"}

    req = session.post(f"https://archiveofourown.org/comments/{comment.id}", data=data)
    if req.status_code == 429:
        raise HTTPError

    soup = BeautifulSoup(req.content, "lxml")
    if "auth error" in soup.title.getText().lower():
        msg = "Invalid authentication token. Try calling session.refresh_auth_token()"
        raise AuthError(msg)

    error = soup.find("div", {"id": "main"}).getText()
    if "you don't have permission" in error.lower():
        msg = "You don't have permission to do this"
        raise PermissionError(msg)


def kudos(work: Work, session: GuestSession) -> bool:
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

    at = work.authenticity_token if work.authenticity_token is not None else session.authenticity_token

    data: Dict[str, Any] = {"authenticity_token": at, "kudo[commentable_id]": work.id, "kudo[commentable_type]": "Work"}
    headers: Dict[str, Any] = {
        "x-csrf-token": work.authenticity_token,
        "x-requested-with": "XMLHttpRequest",
        "referer": f"https://archiveofourown.org/work/{work.id}",
    }
    response = session.post("https://archiveofourown.org/kudos.js", headers=headers, data=data)
    if response.status_code == 429:
        raise HTTPError

    if response.status_code == 201:
        return True  # Success

    if response.status_code == 422:
        json = response.json()
        if "errors" in json:
            if "auth_error" in json["errors"]:
                msg = "Invalid authentication token. Try calling session.refresh_auth_token()"
                raise AuthError(msg)

            if "user_id" in json["errors"] or "ip_address" in json["errors"]:
                return False  # User has already left kudos

            if "no_commentable" in json["errors"]:
                raise InvalidIdError("Invalid ID")
        raise UnexpectedResponseError(f"Unexpected json received:\n" + str(json))

    raise UnexpectedResponseError(f"Unexpected HTTP status code received ({response.status_code})")


def subscribe(subscribable, worktype, session, unsubscribe=False, subid=None):
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
        session = subscribable.session
    if session is None or not session.is_authed:
        raise AuthError("Invalid session")

    if subscribable.authenticity_token is not None:
        at = subscribable.authenticity_token
    else:
        at = session.authenticity_token

    data = {
        "authenticity_token": at,
        "subscription[subscribable_id]": subscribable.id,
        "subscription[subscribable_type]": worktype.capitalize(),
    }

    url = f"https://archiveofourown.org/users/{session.username}/subscriptions"
    if unsubscribe:
        if subid is None:
            raise InvalidIdError("When unsubscribing, subid cannot be None")
        url += f"/{subid}"
        data["_method"] = "delete"
    req = session.session.post(url, data=data, allow_redirects=False)
    if unsubscribe:
        return req
    if req.status_code == 302:
        if req.headers["Location"] == AO3_AUTH_ERROR_URL:
            raise AuthError("Invalid authentication token. Try calling session.refresh_auth_token()")
    else:
        raise InvalidIdError(f"Invalid ID / worktype")


def bookmark(
    bookmarkable: Union[Work, Series],
    session: Optional[Session] = None,
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
        session = bookmarkable.session
    if (session is None) or not session.is_authed:
        msg = "Invalid session"
        raise AuthError(msg)

    at = bookmarkable.authenticity_token if bookmarkable.authenticity_token is not None else session.authenticity_token

    if tags is None:
        tags = []
    if collections is None:
        collections = []

    pseud_id = get_pseud_id(bookmarkable, session, pseud)
    if pseud_id is None:
        raise PseudError("Couldn't find your pseud's id")

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
    bookmarkid: Union[Work, Series],
    session: Optional[Session] = None,
    auth_token: Optional[str] = None,
) -> None:
    """Remove a bookmark from the work/series

    Args:
        bookmarkid (Work/Series): AO3 object
        session (AO3.Session): Session object
        auth_token (str, optional): Authenticity token. Defaults to None.
    """
    if (session is None) or not session.is_authed:
        raise AuthError("Invalid session")

    data: Dict[str, Any] = {
        "authenticity_token": session.authenticity_token if auth_token is None else auth_token,
        "_method": "delete",
    }

    url = f"https://archiveofourown.org/bookmarks/{bookmarkid}"
    req = session.session.post(url, data=data, allow_redirects=False)
    handle_bookmark_errors(req)


def handle_bookmark_errors(request):
    if request.status_code == 302:
        if request.headers["Location"] == AO3_AUTH_ERROR_URL:
            raise AuthError("Invalid authentication token. Try calling session.refresh_auth_token()")
    else:
        if request.status_code == 200:
            soup = BeautifulSoup(request.content, "lxml")
            error_div = soup.find("div", {"id": "error", "class": "error"})
            if error_div is None:
                raise UnexpectedResponseError("An unknown error occurred")

            errors = [item.getText() for item in error_div.findAll("li")]
            if len(errors) == 0:
                raise BookmarkError("An unknown error occurred")
            raise BookmarkError("Error(s) creating bookmark:" + " ".join(errors))

        raise UnexpectedResponseError(f"Unexpected HTTP status code received ({request.status_code})")


def get_pseud_id(
    ao3object: Union[Work, Series, Chapter],
    session: Optional[GuestSession] = None,
    specified_pseud: Optional[str] = None,
):
    if session is None:
        session = ao3object.session
    if session is None or not session.is_authed:
        raise AuthError("Invalid session")

    soup = session.request(ao3object.url)
    pseud = soup.find("input", {"name": re.compile(".+\\[pseud_id\\]")})
    if pseud is None:
        pseud = soup.find("select", {"name": re.compile(".+\\[pseud_id\\]")})
        if pseud is None:
            return None
        pseud_id = None
        if specified_pseud:
            for option in pseud.findAll("option"):
                if option.string == specified_pseud:
                    pseud_id = option.attrs["value"]
                    break
        else:
            for option in pseud.findAll("option"):
                if "selected" in option.attrs and option.attrs["selected"] == "selected":
                    pseud_id = option.attrs["value"]
                    break
    else:
        pseud_id = pseud.attrs["value"]
    return pseud_id


def collect(collectable: Work, session: Optional[Session] = None, collections: Optional[List[str]] = None) -> None:
    """Invites a work to a collection. Be careful, you can collect a work multiple times

    Args:
        work (Work): Work object
        session (AO3.Session): Session object
        collections (list, optional): What collections to add this work to. Defaults to None.
    """

    if session is None:
        session = collectable.session
    if (session is None) or not session.is_authed:
        raise AuthError("Invalid session")

    at = collectable.authenticity_token if collectable.authenticity_token is not None else session.authenticity_token

    if collections is None:
        collections = []

    data: Dict[str, Any] = {"authenticity_token": at, "collection_names": ",".join(collections), "commit": "Add"}

    url = urljoin(collectable.url + "/", "collection_items")
    req = session.session.post(url, data=data, allow_redirects=True)

    if req.status_code == 302:
        if req.headers["Location"] == AO3_AUTH_ERROR_URL:
            raise AuthError("Invalid authentication token. Try calling session.refresh_auth_token()")
    elif req.status_code == 200:
        soup = BeautifulSoup(req.content, "lxml")
        notice_div = soup.find("div", {"class": "notice"})

        error_div = soup.find("div", {"class": "error"})

        if error_div is None and notice_div is None:
            raise UnexpectedResponseError("An unknown error occurred")

        if error_div is not None:
            errors = [item.getText() for item in error_div.findAll("ul")]

            if len(errors) == 0:
                raise CollectError("An unknown error occurred")

            raise CollectError("We couldn't add your submission to the following collection(s): " + " ".join(errors))
    else:
        raise UnexpectedResponseError(f"Unexpected HTTP status code received ({req.status_code})")
