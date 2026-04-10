"""
query.py — Agent-style RAG query loop over indexed PageIndex documents.
"""

from __future__ import annotations

import json
import logging
import os

from config import INDEXER_MODEL, OPENAI_API_BASE, OPENAI_API_KEY
from models import (
    AgentResponse,
    ContextPassage,
    PageContent,
    QueryResponse,
    TraversalStep,
)

logger = logging.getLogger("pageindex_service")

# ---------------------------------------------------------------------------
# System prompt for the agent loop
# ---------------------------------------------------------------------------
_QUERY_SYSTEM_PROMPT = """You are a helpful research assistant with access to three tools:

1. get_document(doc_id)                  – returns document metadata
2. get_document_structure(doc_id)        – returns the full section tree (no text, saves tokens)
3. get_page_content(doc_id, pages)       – returns page text; pages: "5-7", "3,8", or "12"

Strategy:
  • Start with get_document_structure to map the document layout.
  • Identify relevant sections by their page ranges.
  • Call get_page_content for those ranges.
  • Synthesise a clear, accurate answer grounded in the retrieved text.

Always respond with valid JSON matching this schema (no markdown fences):
{
  "tool_call": {"tool": "<name>", "args": {<args>}} or null,
  "answer": "<complete answer>" or null
}

Set tool_call to null and provide a non-null answer when you have enough information.
"""


# ---------------------------------------------------------------------------
# Synchronous agent loop (run in a thread-pool via run_in_executor)
# ---------------------------------------------------------------------------

def run_query_sync(query: str, doc_ids: list[str], client) -> QueryResponse:
    """Execute the agent RAG loop synchronously.
    ``client`` is the PageIndexClient singleton from indexing.py.
    """
    import litellm  # type: ignore[import]

    os.environ["OPENAI_API_BASE"] = OPENAI_API_BASE
    os.environ["OPENAI_API_KEY"]  = OPENAI_API_KEY

    primary_id = doc_ids[0]
    if not client or primary_id not in client.documents:
        return QueryResponse(answer="Document not found.", doc_name="unknown")

    doc_name = client.documents[primary_id].get("doc_name", "")

    if len(doc_ids) > 1:
        doc_listing = "\n".join(
            f"  - doc_id: {did}  |  name: {client.documents[did].get('doc_name', did)}"
            for did in doc_ids
            if client and did in client.documents
        )
        user_content = (
            f"You have {len(doc_ids)} documents available to query:\n"
            f"{doc_listing}\n\n"
            f"Question: {query}"
        )
    else:
        user_content = f"doc_id: {primary_id}\n\nQuestion: {query}"

    messages = [
        {"role": "system", "content": _QUERY_SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]

    traversal: list[TraversalStep] = []
    context:   list[ContextPassage] = []
    answer:    str = ""

    for _ in range(10):
        response = litellm.completion(
            model=INDEXER_MODEL,
            messages=messages,
            temperature=0,
            max_tokens=16384,
        )
        raw_text = response.choices[0].message.content or ""

        parsed = AgentResponse.parse_llm(raw_text)

        if parsed.tool_call:
            tool      = parsed.tool_call.tool
            args      = parsed.tool_call.args
            doc_id    = args.doc_id or primary_id
            pages_arg = args.pages or "1"

            if tool == "get_document":
                result_str = client.get_document(doc_id)

            elif tool == "get_document_structure":
                result_str = client.get_document_structure(doc_id)

            elif tool == "get_page_content":
                result_str = client.get_page_content(doc_id, str(pages_arg))
                try:
                    raw_pages = json.loads(result_str)
                    if isinstance(raw_pages, list):
                        for p in raw_pages:
                            page = PageContent.model_validate(p)
                            context.append(ContextPassage(
                                relevant=True,
                                section_title=f"Page {page.page}",
                                page_number=page.page,
                                passages=[page.content[:500]],
                            ))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            else:
                result_str = json.dumps({"error": f"Unknown tool: {tool}"})

            traversal.append(TraversalStep(
                tool=tool,
                args=args.model_dump(exclude_none=True),
                result_preview=result_str[:200],
            ))
            messages.append({"role": "assistant", "content": raw_text})
            messages.append({"role": "user", "content": f"Tool result for {tool}:\n{result_str}"})

        if parsed.answer:
            answer = parsed.answer
            break

    if not answer:
        answer = "I was unable to produce an answer within the allowed reasoning steps."

    return QueryResponse(answer=answer, traversal=traversal, context=context, doc_name=doc_name)
