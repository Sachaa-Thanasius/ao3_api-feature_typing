from threading import Thread
from typing import Any, Callable, Literal, Protocol, TypeVar, overload
from typing_extensions import TypeAlias

_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)
_A = TypeVar("_A")
_Callable: TypeAlias = Callable[..., Any]

class _ThreadableCallable(Protocol[_T_co]):
    @overload
    def __call__(self, *args: Any, threaded: Literal[False] = ..., **kwargs: Any) -> _T_co: ...
    @overload
    def __call__(self, *args: Any, threaded: Literal[True] = ..., **kwargs: Any) -> Thread: ...
    def __call__(self, *args: Any, threaded: bool = ..., **kwargs: Any) -> Thread | _T_co: ...

def threadable(func: Callable[..., _T]) -> _ThreadableCallable[_T]: ...

class ThreadPool:
    maximum: int | None
    _tasks: list[_Callable]
    _threads: list[Thread]
    def __init__(self, maximum: int | None = ...) -> None: ...
    def add_task(self, task: _Callable) -> None: ...
    @threadable
    def start(self) -> None: ...
