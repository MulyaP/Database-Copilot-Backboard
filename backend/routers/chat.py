import re
import logging
from fastapi import APIRouter, Depends, HTTPException
from models import ChatMessageRequest, ChatExecuteRequest, ChatMessageResponse, QueryStep
from auth import verify_jwt
from supabase_client import supabase
from services import backboard
from services import db as db_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# Matches the first ```sql ... ``` block in any LLM reply
SQL_PATTERN = re.compile(r"```sql\n?([\s\S]*?)```", re.IGNORECASE)

# Read-only query: SELECT or a CTE (WITH ... SELECT ...)
SELECT_PATTERN = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

# Forbidden regardless of user approval
BLOCKED_PATTERN = re.compile(r"\b(DROP|DELETE|TRUNCATE|ALTER)\b", re.IGNORECASE)

# Max auto-SELECT iterations per round (between pauses)
MAX_ITERATIONS = 5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_select(sql: str) -> bool:
    """True for SELECT queries and CTEs (read-only)."""
    return bool(SELECT_PATTERN.match(sql.strip()))


def _fetch_connection(user_id: str) -> dict:
    """Fetch the user's connection record from Supabase. Raises 404 if missing."""
    result = (
        supabase.table("connections")
        .select("backboard_thread_id, connection_string")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not result.data:
        logger.warning("user=%s  No connection record found in Supabase", user_id)
        raise HTTPException(
            status_code=404,
            detail="No database connection found. Please complete onboarding first.",
        )
    return result.data


async def _run_agentic_loop(
    thread_id: str,
    connection_string: str,
    start_message: str,
    user_id: str,
) -> ChatMessageResponse:
    """
    Shared agentic loop logic used by both /message and /execute.

    Behaviour per SQL type found in an LLM reply:
      - SELECT / CTE  → executed automatically, result fed back, loop continues
      - INSERT/UPDATE → loop PAUSES, returns needs_approval with the pending SQL
      - DROP/DELETE/etc → blocked server-side, LLM notified, loop continues
      - No SQL         → final answer, returns done

    Returns a ChatMessageResponse with status "done" or "needs_approval".
    """
    current_message = start_message
    completed_steps: list[QueryStep] = []

    for iteration in range(1, MAX_ITERATIONS + 1):
        logger.info(
            "user=%s  Iteration %d/%d — sending to Backboard (msg length=%d)",
            user_id, iteration, MAX_ITERATIONS, len(current_message),
        )

        try:
            reply = await backboard.send_message(thread_id, current_message, memory="Auto")
        except Exception as e:
            logger.exception("user=%s  Backboard call failed on iteration %d", user_id, iteration)
            raise HTTPException(status_code=502, detail=f"Failed to get AI response: {str(e)}")

        logger.debug("user=%s  Iteration %d reply (%.300s)", user_id, iteration, reply)

        sql_match = SQL_PATTERN.search(reply)
        if not sql_match:
            logger.info(
                "user=%s  No SQL in iteration %d — final answer. Steps so far: %d",
                user_id, iteration, len(completed_steps),
            )
            return ChatMessageResponse(
                status="done",
                reply=reply,
                completed_steps=completed_steps,
            )

        sql = sql_match.group(1).strip()
        logger.info("user=%s  Iteration %d — SQL detected (%.120r)", user_id, iteration, sql)

        # ── Block forbidden keywords ──────────────────────────────────────
        blocked_match = BLOCKED_PATTERN.search(sql)
        if blocked_match:
            kw = blocked_match.group().upper()
            logger.warning("user=%s  Iteration %d — BLOCKED keyword %r", user_id, iteration, kw)
            step = QueryStep(
                sql=sql,
                error=f"Blocked server-side: '{kw}' is not permitted.",
                kind="blocked",
            )
            completed_steps.append(step)
            current_message = (
                f"That query was blocked because '{kw}' is not permitted. "
                f"Only SELECT, INSERT, and UPDATE are allowed. Please revise your approach."
            )
            continue

        # ── Auto-run SELECT queries ───────────────────────────────────────
        if _is_select(sql):
            logger.info("user=%s  Iteration %d — auto-running SELECT", user_id, iteration)
            try:
                columns, rows = db_service.execute_query(connection_string, sql)
                logger.info(
                    "user=%s  Iteration %d — SELECT returned %d row(s), %d col(s)",
                    user_id, iteration, len(rows), len(columns),
                )
                step = QueryStep(sql=sql, columns=columns, rows=rows, kind="auto")
                completed_steps.append(step)
                current_message = _format_results_for_llm(sql, columns, rows)
            except ValueError as e:
                logger.error("user=%s  Iteration %d — SELECT failed: %s", user_id, iteration, e)
                step = QueryStep(sql=sql, error=str(e), kind="auto")
                completed_steps.append(step)
                current_message = (
                    f"The query failed with this error:\n{str(e)}\n\n"
                    f"Please fix the SQL and try again."
                )
            continue

        # ── Pause for user approval (INSERT / UPDATE) ─────────────────────
        logger.info(
            "user=%s  Iteration %d — write query needs user approval: %.80r",
            user_id, iteration, sql,
        )
        return ChatMessageResponse(
            status="needs_approval",
            pending_sql=sql,
            completed_steps=completed_steps,
        )

    # ── Max iterations reached ────────────────────────────────────────────
    logger.warning("user=%s  Max iterations (%d) reached — requesting summary", user_id, MAX_ITERATIONS)
    try:
        final_reply = await backboard.send_message(
            thread_id,
            "You have reached the maximum number of allowed queries. "
            "Please summarise what you have found so far and give your best answer "
            "without running any more queries.",
            memory="Auto",
        )
    except Exception:
        logger.exception("user=%s  Failed to get final summary after max iterations", user_id)
        final_reply = (
            "I reached the query limit while gathering data. "
            "Please ask a more specific question."
        )

    return ChatMessageResponse(
        status="done",
        reply=final_reply,
        completed_steps=completed_steps,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/message", response_model=ChatMessageResponse)
async def send_chat_message(
    body: ChatMessageRequest,
    user_id: str = Depends(verify_jwt),
):
    """
    Start an agentic chat round.
    SELECTs run automatically; INSERT/UPDATE pauses for user approval.
    """
    logger.info(
        "user=%s  /chat/message — length=%d  preview: %.80r",
        user_id, len(body.message), body.message,
    )
    conn = _fetch_connection(user_id)
    return await _run_agentic_loop(
        thread_id=conn["backboard_thread_id"],
        connection_string=conn["connection_string"],
        start_message=body.message,
        user_id=user_id,
    )


@router.post("/execute", response_model=ChatMessageResponse)
async def execute_pending_query(
    body: ChatExecuteRequest,
    user_id: str = Depends(verify_jwt),
):
    """
    Resume the agentic loop after the user approves or rejects a pending write query.

    - approved=True  → execute the SQL, feed result to LLM, continue loop
    - approved=False → tell LLM the query was rejected, continue loop
    """
    logger.info(
        "user=%s  /chat/execute — approved=%s  SQL: %.80r",
        user_id, body.approved, body.sql,
    )
    conn = _fetch_connection(user_id)
    thread_id = conn["backboard_thread_id"]
    connection_string = conn["connection_string"]

    if body.approved:
        # Run the query and format the result for the LLM
        logger.info("user=%s  Executing approved write query", user_id)
        try:
            columns, rows = db_service.execute_query(connection_string, body.sql)
            logger.info(
                "user=%s  Approved write executed — %d col(s), %d row(s)",
                user_id, len(columns), len(rows),
            )
            approved_step = QueryStep(sql=body.sql, columns=columns, rows=rows, kind="approved")
            next_message = _format_results_for_llm(body.sql, columns, rows)
        except ValueError as e:
            logger.error("user=%s  Approved write failed: %s", user_id, e)
            approved_step = QueryStep(sql=body.sql, error=str(e), kind="approved")
            next_message = (
                f"The write query failed with this error:\n{str(e)}\n\n"
                f"Please adjust your approach."
            )
    else:
        # User rejected — do not run the query
        logger.info("user=%s  User rejected the write query", user_id)
        approved_step = QueryStep(
            sql=body.sql,
            error="Rejected by user.",
            kind="rejected",
        )
        next_message = (
            "The user reviewed your proposed SQL query and chose NOT to run it. "
            "Please provide your best answer based on the information you already have, "
            "or propose a different approach if needed."
            "Do not ask the user to run the same query again please."
        )

    # Resume the loop from the outcome of the user's decision
    response = await _run_agentic_loop(
        thread_id=thread_id,
        connection_string=connection_string,
        start_message=next_message,
        user_id=user_id,
    )

    # Prepend the just-decided step so the frontend has the full picture
    response.completed_steps.insert(0, approved_step)
    return response


# ── Result formatter ──────────────────────────────────────────────────────────

def _format_results_for_llm(sql: str, columns: list[str], rows: list[list]) -> str:
    """
    Render query results as readable markdown for the LLM.
    Write ops (no RETURNING) come back with columns=["rows_affected"].
    SELECT / RETURNING results are rendered as a capped markdown table.
    """
    lines: list[str] = [
        "Here are the results of the SQL statement you ran:",
        "```sql",
        sql,
        "```",
        "",
    ]

    if columns == ["rows_affected"]:
        affected = rows[0][0] if rows else 0
        lines.append(f"**Write successful. {affected} row(s) affected.**")
        lines.append("")
        lines.append(
            "The write has been committed. Run another query to verify the change, "
            "or provide your final answer in plain text with no SQL blocks."
        )
        return "\n".join(lines)

    if not rows:
        lines.append("The query returned **0 rows**.")
    else:
        lines.append("| " + " | ".join(str(c) for c in columns) + " |")
        lines.append("|" + "|".join(" --- " for _ in columns) + "|")
        for row in rows[:50]:
            cells = (str(v) if v is not None else "NULL" for v in row)
            lines.append("| " + " | ".join(cells) + " |")
        if len(rows) > 50:
            lines.append("")
            lines.append(f"*({len(rows) - 50} additional rows not shown)*")
        lines.append("")
        lines.append(f"**Total rows returned: {len(rows)}**")

    lines.append("")
    lines.append(
        "Based on these results, either run another query if you need more data, "
        "or provide your final answer in plain text with no SQL blocks."
    )
    return "\n".join(lines)
