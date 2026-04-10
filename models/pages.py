from __future__ import annotations

from pydantic import BaseModel


class PageContent(BaseModel):
    """One page's content as returned by PageIndex's get_page_content."""

    page: int
    content: str = ""
