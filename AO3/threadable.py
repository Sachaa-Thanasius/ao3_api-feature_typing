from threading import Thread
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, Protocol, TypeVar, Union, overload


if TYPE_CHECKING:
    from typing_extensions import TypeAlias


T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
A = TypeVar("A")
Callable_alias: TypeAlias = Callable[..., Any]


class ThreadableCallable(Protocol[T_co]):
    @overload
    def __call__(self, *args: Any, threaded: Literal[False] = ..., **kwargs: Any) -> T_co:
        ...

    @overload
    def __call__(self, *args: Any, threaded: Literal[True] = ..., **kwargs: Any) -> Thread:
        ...

    def __call__(self, *args: Any, threaded: bool = False, **kwargs: Any) -> Union[Thread, T_co]:
        ...


def threadable(func: Callable[..., T]) -> ThreadableCallable[T]:
    """Allows the function to be ran as a thread using the 'threaded' argument"""

    @overload
    def wrapped(*args: Any, threaded: Literal[False] = ..., **kwargs: Any) -> T:
        ...

    @overload
    def wrapped(*args: Any, threaded: Literal[True] = ..., **kwargs: Any) -> Thread:
        ...

    def wrapped(*args: Any, threaded: bool = False, **kwargs: Any) -> Union[Thread, T]:
        if threaded:
            thread = Thread(target=func, args=args, kwargs=kwargs)
            thread.start()
            return thread
        return func(*args, **kwargs)

    wrapped.__module__ = func.__module__
    wrapped.__name__ = func.__name__
    wrapped.__qualname__ = func.__qualname__
    wrapped.__doc__ = func.__doc__
    wrapped._threadable = True  # type: ignore
    return wrapped


class ThreadPool:
    def __init__(self, maximum: Optional[int] = None) -> None:
        self.maximum = maximum
        self._tasks: list[Callable_alias] = []
        self._threads: list[Thread] = []

    def add_task(self, task: Callable_alias) -> None:
        self._tasks.append(task)

    @threadable
    def start(self) -> None:
        while len(self._threads) != 0 or len(self._tasks) != 0:
            self._threads[:] = filter(lambda thread: thread.is_alive(), self._threads)
            maximum = self.maximum or (len(self._threads) * 2)
            for _ in range(min(maximum - len(self._threads), len(self._tasks))):
                self._threads.append(self._tasks.pop(0)(threaded=True))
