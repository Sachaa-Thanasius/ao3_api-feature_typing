from collections.abc import Callable
from functools import partial
from typing import Any, Final

from .threadable import threadable

def _download_languages() -> None: ...
def _download_fandom(fandom_key: str, name: str) -> None: ...

_FANDOM_RESOURCES: Final[dict[str, partial[None]]]

_LANGUAGE_RESOURCES: Final[dict[str, Callable[[], None]]]

_RESOURCE_DICTS: Final[list[tuple[str, dict[str, Any]]]]

@threadable
def download(resource: str) -> None: ...
def get_resources() -> dict[str, list[str]]: ...
def has_resource(resource: str) -> bool: ...
@threadable
def download_all(redownload: bool = ...) -> None: ...
@threadable
def download_all_threaded(redownload: bool = ...) -> None: ...
