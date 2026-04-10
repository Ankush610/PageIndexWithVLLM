"""
Pydantic models for the PageIndex FastAPI service.

Every JSON boundary in the service is typed here. Import directly from
this package — submodule layout is an implementation detail:

    from models import AgentResponse, QueryRequest, UploadSettings, ...
"""

from .agent import AgentResponse, ToolCall, ToolCallArgs
from .documents import DeleteResponse, DocumentsResponse, DocumentSummary, HealthResponse
from .pages import PageContent
from .query import ContextPassage, QueryRequest, QueryResponse, TraversalStep
from .upload import UploadFileResult, UploadResponse, UploadSettings

__all__ = [
    # agent
    "AgentResponse",
    "ToolCall",
    "ToolCallArgs",
    # documents
    "DeleteResponse",
    "DocumentsResponse",
    "DocumentSummary",
    "HealthResponse",
    # pages
    "PageContent",
    # query
    "ContextPassage",
    "QueryRequest",
    "QueryResponse",
    "TraversalStep",
    # upload
    "UploadFileResult",
    "UploadResponse",
    "UploadSettings",
]
