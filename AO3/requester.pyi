import threading
from typing import Any

from requests import Response

class Requester:
    requests: list[float]
    _lock: threading.Lock
    total: int

    def __init__(self, rqtw: int = ..., timew: int = ...) -> None: ...
    @property
    def rqtw(self) -> int: ...
    @rqtw.setter
    def rqtw(self, value: int) -> None: ...

    setRQTW = rqtw.fset

    @property
    def timew(self) -> int: ...
    @timew.setter
    def timew(self, value: int) -> None: ...

    setTimeW = timew.fset

    def request(self, *args: Any, **kwargs: Any) -> Response: ...

requester = Requester()
