import threading
import time
from typing import TYPE_CHECKING, Any, List

import requests


if TYPE_CHECKING:
    from .session import GuestSession


class Requester:
    """Requester object"""

    def __init__(self, rqtw: int = -1, timew: int = 60):
        """Limits the request rate to prevent HTTP 429 (rate limiting) responses.
        12 request per minute seems to be the limit.

        Args:
            rqm (int, optional): Maximum requests per time window (-1 -> no limit). Defaults to -1.
            timew (int, optional): Time window (seconds). Defaults to 60.
        """

        self._requests: List[float] = []
        self.rqtw = rqtw
        self.timew = timew
        self._lock = threading.Lock()
        self.total = 0

    @property
    def rqtw(self) -> int:
        return self._rqtw

    @rqtw.setter
    def rqtw(self, value: int) -> None:
        self._rqtw = value

    @property
    def timew(self) -> int:
        return self._timew

    @timew.setter
    def timew(self, value: int) -> None:
        self._timew = value

    def request(self, *args: Any, **kwargs: Any) -> requests.Response:
        """Requests a web page once enough time has passed since the last request

        Args:
            session(requests.Session, optional): Session object to request with

        Returns:
            requests.Response: Response object
        """

        # We've made a bunch of requests, time to rate limit?
        if self._rqtw != -1:
            with self._lock:
                if len(self._requests) >= self._rqtw:
                    t = time.time()
                    # Reduce list to only requests made within the current time window
                    while len(self._requests):
                        if t - self._requests[0] >= self._timew:
                            self._requests.pop(0)  # Older than window, forget about it
                        else:
                            break  # Inside window, the rest of them must be too
                    # Have we used up all available requests within our window?
                    if len(self._requests) >= self._rqtw:  # Yes
                        # Wait until the oldest request exits the window, giving us a slot for the new one
                        time.sleep(self._requests[0] + self._timew - t)
                        # Now outside window, drop it
                        self._requests.pop(0)

                if self._rqtw != -1:
                    self._requests.append(time.time())
                self.total += 1
        if "session" in kwargs:
            sess: GuestSession = kwargs.pop("session")
            req = sess.request(*args, **kwargs)
        else:
            req = requests.request(*args, **kwargs)

        return req


requester = Requester()
