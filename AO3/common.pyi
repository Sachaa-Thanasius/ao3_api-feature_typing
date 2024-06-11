from typing import Any

from bs4 import Tag

from .works import Work

def __setifnotnone(obj: object, attr: str, value: Any) -> None: ...
def get_work_from_banner(work: Tag) -> Work: ...
