"""Generic pagination helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel


class Page[T](BaseModel):
    """A page of results with navigation metadata."""

    items: list[T]
    total: int
    page: int
    size: int
    pages: int

    @classmethod
    def create(cls, items: list[T], *, total: int, page: int, size: int) -> Page[T]:
        pages = (total + size - 1) // size if size > 0 else 0
        return cls(items=items, total=total, page=page, size=size, pages=pages)


class PageParams(BaseModel):
    """Validated pagination query parameters."""

    page: int = 1
    size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


def page_params(
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    size: Annotated[int, Query(ge=1, le=1000, description="Items per page (max 1000)")] = 20,
) -> PageParams:
    """FastAPI dependency for pagination query parameters."""
    return PageParams(page=page, size=size)
