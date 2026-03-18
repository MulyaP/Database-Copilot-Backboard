import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from models import ChatMessageRequest, ChatExecuteRequest, ChatMessageResponse, QueryStep
from auth import verify_jwt
from supabase_client import supabase
from services import db as db_service
from services import schema as schema_service
from services import history
from services import groq_llm
from limiter import limiter
import re

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# ── Safety patterns ────────────────────────────────────────────────────────────

# Read-only queries: SELECT or CTEs (WITH ... SELECT ...)
SELECT_PATTERN = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

# Write queries that need user approval
WRITE_PATTERN = re.compile(r"^\s*(INSERT|UPDATE)\b", re.IGNORECASE)

# Forbidden regardless of user approval.
# Covers: destructive DML, DDL, privilege management, and execution commands.
BLOCKED_PATTERN = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|ALTER|CREATE|REPLACE|MERGE"
    r"|GRANT|REVOKE"
    r"|EXEC|EXECUTE|CALL"
    r"|LOAD|COPY|IMPORT|EXPORT"
    r"|ATTACH|DETACH)\b",
    re.IGNORECASE,
)

# ── Loop limits ────────────────────────────────────────────────────────────────

# Max Groq calls (tool executions) per user round.
MAX_ITERATIONS = 8

# Max cumulative result cells (rows × columns) across all queries in one round.
MAX_TOTAL_CELLS = 5_000

# Max consecutive unproductive iterations before forcing a final answer.
MAX_UNPRODUCTIVE_STREAK = 3

# Wall-clock timeout for one complete agentic round, in seconds.
LOOP_TIMEOUT_SECONDS = 120.0

# ── System prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT_TEMPLATE = """\
You are a Database Copilot. You help developers query and understand their database using plain English.

## Database Schema
{schema}

## How to work
You have access to one tool: `execute_sql`. Use it to run SQL queries against the user's database.

Rules:
- Use `execute_sql` for SELECT, INSERT, and UPDATE queries.
- For INSERT operations that need the generated ID, use a RETURNING clause.
- Forbidden (blocked server-side): DROP, DELETE, TRUNCATE, ALTER, CREATE, REPLACE, MERGE, GRANT, REVOKE, EXEC, EXECUTE, CALL, LOAD, COPY, IMPORT, EXPORT, ATTACH, DETACH.
- Run one query at a time. After seeing the results, decide whether to run another or give a final answer.
- When you have enough information, reply in plain text with no tool calls.
- Be concise and accurate.\
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_system_message(schema: str) -> dict:
    return {"role": "system", "content": _SYSTEM_PROMPT_TEMPLATE.format(schema=schema)}


def _fetch_connection(user_id: str) -> dict:
    """Fetch the user's connection record from Supabase. Raises 404 if missing."""
    result = (
        supabase.table("connections")
        .select("connection_string")
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


def _get_or_introspect_schema(user_id: str, connection_string: str) -> str:
    """
    Return the cached schema for this user.
    If the cache is empty (server restart), re-introspect from the connection string.
    """
    schema = history.get_schema(user_id)
    if schema:
        return schema
    logger.info("user=%s  Schema not in cache — re-introspecting", user_id)
    try:
        schema = schema_service.introspect_schema(connection_string)
        history.set_schema(user_id, schema)
        return schema
    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to re-introspect database schema: {str(e)}",
        )


def _format_results_for_llm(sql: str, columns: list[str], rows: list[list]) -> str:
    """Render query results as plain text for the LLM tool result."""
    if columns == ["rows_affected"]:
        affected = rows[0][0] if rows else 0
        return f"Write successful. {affected} row(s) affected."

    if not rows:
        return "The query returned 0 rows."

    lines: list[str] = []
    lines.append("| " + " | ".join(str(c) for c in columns) + " |")
    lines.append("|" + "|".join(" --- " for _ in columns) + "|")
    for row in rows[:50]:
        cells = (str(v) if v is not None else "NULL" for v in row)
        lines.append("| " + " | ".join(cells) + " |")
    if len(rows) > 50:
        lines.append(f"({len(rows) - 50} additional rows not shown)")
    lines.append(f"Total rows returned: {len(rows)}")
    return "\n".join(lines)


async def _request_final_answer(
    user_id: str,
    productive_steps: int,
    completed_steps: list[QueryStep],
    system_msg: dict,
) -> ChatMessageResponse:
    """
    Ask Groq for a final text answer after the loop has exhausted its budget.
    Prompt wording depends on whether any useful data was gathered.
    """
    if productive_steps > 0:
        prompt = (
            "You have reached the query limit. "
            "Summarise what you found and give your best final answer in plain text. "
            "Do not call any tools."
        )
        fallback = "I reached the query limit while gathering data. Please ask a more specific question."
    else:
        prompt = (
            "You were unable to retrieve any useful data from the database. "
            "Honestly tell the user that you could not find the requested information. "
            "Do not invent or guess an answer. Give your response in plain text. "
            "Do not call any tools."
        )
        fallback = "I was unable to find the information you requested. Please try rephrasing your question."

    history.append_messages(user_id, {"role": "user", "content": prompt})
    messages = [system_msg] + history.get_history(user_id)
    try:
        final_msg = await groq_llm.chat(messages)
        history.append_messages(user_id, final_msg)
        reply = final_msg.get("content") or fallback
    except Exception:
        logger.exception("user=%s  Failed to get final answer from Groq", user_id)
        reply = fallback

    return ChatMessageResponse(status="done", reply=reply, completed_steps=completed_steps)


async def _run_agentic_loop(
    connection_string: str,
    user_id: str,
) -> ChatMessageResponse:
    """
    Core agentic loop using Groq native tool calling.

    History for this user must already contain the initiating message(s) before
    this function is called — either a user message (from /message) or a tool
    result (from /execute after approval).

    Behaviour per tool call:
      - SELECT / CTE  → executed automatically, result appended as tool result
      - INSERT/UPDATE → loop pauses, returns needs_approval with pending SQL
      - DROP/DELETE/etc → blocked; error returned as tool result, loop continues
      - No tool call   → LLM gave final text answer, returns done

    Stopping criteria:
      1. Natural stop        — no tool calls in LLM response → "done"
      2. Write query         — INSERT/UPDATE → "needs_approval"
      3. Blocked keyword     — forbidden SQL → error fed back, streak++
      4. Cycle detection     — duplicate SQL → error fed back, streak++
      5. Unproductive streak — MAX_UNPRODUCTIVE_STREAK consecutive bad iterations
      6. Cell budget         — cumulative cells exceed MAX_TOTAL_CELLS
      7. Iteration cap       — MAX_ITERATIONS reached → forced final answer
    """
    schema = _get_or_introspect_schema(user_id, connection_string)
    system_msg = _build_system_message(schema)

    completed_steps: list[QueryStep] = []
    seen_sql: set[str] = set()
    total_cells: int = 0
    unproductive_streak: int = 0
    productive_steps: int = 0

    for iteration in range(1, MAX_ITERATIONS + 1):
        messages = [system_msg] + history.get_history(user_id)
        logger.info(
            "user=%s  Iteration %d/%d — calling Groq (%d messages in context)",
            user_id, iteration, MAX_ITERATIONS, len(messages),
        )

        try:
            assistant_msg = await groq_llm.chat(messages)
        except Exception as e:
            logger.exception("user=%s  Groq call failed on iteration %d", user_id, iteration)
            raise HTTPException(status_code=502, detail=f"Failed to get AI response: {str(e)}")

        # Always append the assistant message to history before processing it.
        history.append_messages(user_id, assistant_msg)

        tool_calls = assistant_msg.get("tool_calls")

        if not tool_calls:
            # No tool call → LLM has given its final text answer.
            reply = assistant_msg.get("content") or ""
            logger.info(
                "user=%s  Iteration %d — final answer received (%d chars)",
                user_id, iteration, len(reply),
            )
            return ChatMessageResponse(
                status="done",
                reply=reply,
                completed_steps=completed_steps,
            )

        if len(tool_calls) > 1:
            logger.warning(
                "user=%s  Iteration %d — %d tool_calls returned; processing first only",
                user_id, iteration, len(tool_calls),
            )

        tc = tool_calls[0]
        tool_call_id = tc["id"]

        # ── Parse SQL from tool call arguments ────────────────────────────
        try:
            args = json.loads(tc["function"]["arguments"])
            sql = args.get("sql", "").strip()
        except (json.JSONDecodeError, KeyError):
            logger.error(
                "user=%s  Iteration %d — failed to parse tool call arguments: %r",
                user_id, iteration, tc["function"]["arguments"],
            )
            history.append_messages(user_id, {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": "Error: could not parse the SQL from your tool call arguments. Please try again.",
            })
            unproductive_streak += 1
            if unproductive_streak >= MAX_UNPRODUCTIVE_STREAK:
                break
            continue

        if not sql:
            logger.warning("user=%s  Iteration %d — empty SQL in tool call", user_id, iteration)
            history.append_messages(user_id, {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": "Error: no SQL statement was provided.",
            })
            unproductive_streak += 1
            if unproductive_streak >= MAX_UNPRODUCTIVE_STREAK:
                break
            continue

        logger.info("user=%s  Iteration %d — SQL: %.120r", user_id, iteration, sql)

        # ── Block forbidden keywords ───────────────────────────────────────
        blocked_match = BLOCKED_PATTERN.search(sql)
        if blocked_match:
            kw = blocked_match.group().upper()
            logger.warning("user=%s  Iteration %d — BLOCKED keyword %r", user_id, iteration, kw)
            step = QueryStep(sql=sql, error=f"Blocked: '{kw}' is not permitted.", kind="blocked")
            completed_steps.append(step)
            unproductive_streak += 1
            history.append_messages(user_id, {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": (
                    f"Error: '{kw}' is not permitted. "
                    "Only SELECT, INSERT, and UPDATE are allowed. "
                    "DDL, privilege management, and execution commands are blocked server-side."
                ),
            })
            if unproductive_streak >= MAX_UNPRODUCTIVE_STREAK:
                break
            continue

        # ── Cycle detection ────────────────────────────────────────────────
        sql_key = " ".join(sql.lower().split())
        if sql_key in seen_sql:
            logger.warning("user=%s  Iteration %d — duplicate SQL, skipping", user_id, iteration)
            step = QueryStep(sql=sql, error="Duplicate query.", kind="blocked")
            completed_steps.append(step)
            unproductive_streak += 1
            history.append_messages(user_id, {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": (
                    "You already ran that exact query and have its results. "
                    "Use what you know to give a final answer, or try a meaningfully different query."
                ),
            })
            if unproductive_streak >= MAX_UNPRODUCTIVE_STREAK:
                break
            continue

        seen_sql.add(sql_key)

        # ── Pause for user approval (INSERT / UPDATE) ──────────────────────
        if WRITE_PATTERN.search(sql):
            logger.info("user=%s  Iteration %d — write query needs user approval", user_id, iteration)
            # Store SQL server-side so /execute retrieves it from state, not from
            # the client request (which could be tampered with).
            history.set_pending_sql(user_id, sql)
            return ChatMessageResponse(
                status="needs_approval",
                pending_sql=sql,
                completed_steps=completed_steps,
            )

        # ── Auto-run SELECT / CTE ──────────────────────────────────────────
        if SELECT_PATTERN.match(sql):
            logger.info("user=%s  Iteration %d — auto-running SELECT", user_id, iteration)
            try:
                columns, rows = db_service.execute_query(connection_string, sql)
                logger.info(
                    "user=%s  Iteration %d — SELECT returned %d row(s), %d col(s)",
                    user_id, iteration, len(rows), len(columns),
                )
                step = QueryStep(sql=sql, columns=columns, rows=rows, kind="auto")
                completed_steps.append(step)

                if rows:
                    productive_steps += 1
                    unproductive_streak = 0
                else:
                    unproductive_streak += 1

                total_cells += len(columns) * len(rows)
                result_text = _format_results_for_llm(sql, columns, rows)

                history.append_messages(user_id, {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result_text,
                })

                # Cell budget exceeded — ask for final answer now.
                if total_cells >= MAX_TOTAL_CELLS:
                    logger.warning(
                        "user=%s  Cell budget exceeded (%d total cells) — forcing final answer",
                        user_id, total_cells,
                    )
                    budget_prompt = (
                        "You have retrieved a large volume of data across multiple queries. "
                        "Please give your final answer now in plain text. Do not call any tools."
                    )
                    history.append_messages(user_id, {"role": "user", "content": budget_prompt})
                    final_messages = [system_msg] + history.get_history(user_id)
                    try:
                        final_msg = await groq_llm.chat(final_messages)
                        history.append_messages(user_id, final_msg)
                        reply = final_msg.get("content") or (
                            "I retrieved a large volume of data. Please ask a more specific question."
                        )
                    except Exception:
                        logger.exception("user=%s  Failed to get final answer after cell budget exceeded", user_id)
                        reply = "I retrieved a large volume of data. Please ask a more specific question."
                    return ChatMessageResponse(status="done", reply=reply, completed_steps=completed_steps)

                if unproductive_streak >= MAX_UNPRODUCTIVE_STREAK:
                    logger.warning(
                        "user=%s  Unproductive streak of %d (empty results) — stopping early",
                        user_id, unproductive_streak,
                    )
                    break

            except ValueError as e:
                logger.error("user=%s  Iteration %d — SELECT failed: %s", user_id, iteration, e)
                step = QueryStep(sql=sql, error=str(e), kind="auto")
                completed_steps.append(step)
                unproductive_streak += 1
                history.append_messages(user_id, {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": f"Error executing query: {str(e)}",
                })
                if unproductive_streak >= MAX_UNPRODUCTIVE_STREAK:
                    logger.warning(
                        "user=%s  Unproductive streak of %d (query errors) — stopping early",
                        user_id, unproductive_streak,
                    )
                    break

            continue

        # ── Unknown SQL type (not SELECT/INSERT/UPDATE) ────────────────────
        logger.warning(
            "user=%s  Iteration %d — unrecognized SQL type: %.60r",
            user_id, iteration, sql,
        )
        history.append_messages(user_id, {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": "Only SELECT, INSERT, and UPDATE are permitted. Please revise your query.",
        })
        unproductive_streak += 1
        if unproductive_streak >= MAX_UNPRODUCTIVE_STREAK:
            break

    # ── Loop exhausted ─────────────────────────────────────────────────────────
    logger.warning(
        "user=%s  Loop ended — productive_steps=%d  unproductive_streak=%d — requesting final answer",
        user_id, productive_steps, unproductive_streak,
    )
    return await _request_final_answer(user_id, productive_steps, completed_steps, system_msg)


# ── Timeout wrapper ────────────────────────────────────────────────────────────

async def _run_with_timeout(coro, user_id: str) -> ChatMessageResponse:
    """Run an agentic loop coroutine with a wall-clock timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=LOOP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(
            "user=%s  Agentic loop timed out after %.0fs", user_id, LOOP_TIMEOUT_SECONDS
        )
        raise HTTPException(
            status_code=504,
            detail=(
                "The request timed out. Your query is taking too long — "
                "try asking a more specific question."
            ),
        )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/message", response_model=ChatMessageResponse)
@limiter.limit("20/minute")
async def send_chat_message(
    request: Request,
    body: ChatMessageRequest,
    user_id: str = Depends(verify_jwt),
):
    """
    Start an agentic chat round.
    SELECTs run automatically; INSERT/UPDATE pauses for user approval.
    """
    logger.info("user=%s  /chat/message — length=%d chars", user_id, len(body.message))
    logger.debug("user=%s  /chat/message content preview: %.80r", user_id, body.message)
    conn = _fetch_connection(user_id)

    # Append the user's message to history before entering the loop.
    history.append_messages(user_id, {"role": "user", "content": body.message})

    return await _run_with_timeout(
        _run_agentic_loop(
            connection_string=conn["connection_string"],
            user_id=user_id,
        ),
        user_id=user_id,
    )


@router.post("/execute", response_model=ChatMessageResponse)
@limiter.limit("30/minute")
async def execute_pending_query(
    request: Request,
    body: ChatExecuteRequest,
    user_id: str = Depends(verify_jwt),
):
    """
    Resume the agentic loop after the user approves or rejects a pending write query.

    - approved=True  → execute the SQL, append result, continue loop
    - approved=False → tell LLM the query was rejected, continue loop
    """
    logger.info("user=%s  /chat/execute — approved=%s", user_id, body.approved)
    conn = _fetch_connection(user_id)
    connection_string = conn["connection_string"]

    # Retrieve SQL from server-side state — never trust body.sql for execution.
    sql = history.get_pending_sql(user_id)
    if not sql:
        logger.error("user=%s  /chat/execute — no pending SQL found in server state", user_id)
        raise HTTPException(
            status_code=400,
            detail="No pending query found. Please start a new message.",
        )

    # Find the tool_call_id from the pending assistant message in history.
    tool_call_id = history.get_pending_tool_call_id(user_id)
    if not tool_call_id:
        logger.error("user=%s  /chat/execute — no pending tool call found in history", user_id)
        raise HTTPException(
            status_code=400,
            detail="No pending query found. Please start a new message.",
        )

    history.clear_pending_sql(user_id)
    logger.debug("user=%s  /chat/execute SQL (server-side): %.80r", user_id, sql)

    if body.approved:
        logger.info("user=%s  Executing approved write query", user_id)
        try:
            columns, rows = db_service.execute_query(connection_string, sql)
            logger.info(
                "user=%s  Approved write executed — %d col(s), %d row(s)",
                user_id, len(columns), len(rows),
            )
            approved_step = QueryStep(sql=sql, columns=columns, rows=rows, kind="approved")
            result_text = _format_results_for_llm(sql, columns, rows)
        except ValueError as e:
            logger.error("user=%s  Approved write failed: %s", user_id, e)
            approved_step = QueryStep(sql=sql, error=str(e), kind="approved")
            result_text = f"Error executing the approved query: {str(e)}"
    else:
        logger.info("user=%s  User rejected the write query", user_id)
        approved_step = QueryStep(sql=sql, error="Rejected by user.", kind="rejected")
        result_text = (
            "The user reviewed your proposed query and chose NOT to run it. "
            "Please provide your best answer based on the information you already have, "
            "or propose a different approach if needed."
        )

    # Append the tool result to history so the loop can continue.
    history.append_messages(user_id, {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": result_text,
    })

    response = await _run_with_timeout(
        _run_agentic_loop(
            connection_string=connection_string,
            user_id=user_id,
        ),
        user_id=user_id,
    )

    # Prepend the just-decided step so the frontend has the full picture.
    response.completed_steps.insert(0, approved_step)
    return response
