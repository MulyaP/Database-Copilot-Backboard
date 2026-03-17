from pydantic import BaseModel
from typing import List, Any, Optional


class ConnectRequest(BaseModel):
    connection_string: str


class ConnectResponse(BaseModel):
    success: bool


class ChatMessageRequest(BaseModel):
    message: str


class QueryStep(BaseModel):
    """One step in the agentic loop — a SQL statement and its outcome."""
    sql: str
    columns: List[str] = []
    rows: List[List[Any]] = []
    error: Optional[str] = None
    # How this step was executed:
    #   "auto"     — SELECT, run automatically
    #   "approved" — INSERT/UPDATE, user approved
    #   "rejected" — INSERT/UPDATE, user rejected (not run)
    #   "blocked"  — DROP/DELETE/etc., rejected server-side
    kind: str = "auto"


class ChatMessageResponse(BaseModel):
    """
    Returned by both POST /chat/message and POST /chat/execute.

    status == "done":
        reply            — the LLM's final answer text
        completed_steps  — all steps executed in this round

    status == "needs_approval":
        pending_sql      — the write SQL the LLM wants to run
        completed_steps  — SELECT steps that already ran before the pause
    """
    status: str               # "done" | "needs_approval"
    reply: str = ""
    pending_sql: str = ""
    completed_steps: List[QueryStep] = []


class ChatExecuteRequest(BaseModel):
    """Sent by the frontend after the user decides on a pending write query."""
    approved: bool
    sql: Optional[str] = None  # display-only; execution uses server-side pending SQL


class QueryRunRequest(BaseModel):
    sql: str


class QueryRunResponse(BaseModel):
    columns: List[str]
    rows: List[List[Any]]
