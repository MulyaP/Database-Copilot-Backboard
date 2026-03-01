import logging
from fastapi import APIRouter, Depends, HTTPException
from models import ConnectRequest, ConnectResponse
from auth import verify_jwt
from supabase_client import supabase
from services import schema as schema_service
from services import backboard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/connect", response_model=ConnectResponse)
async def connect_database(
    body: ConnectRequest,
    user_id: str = Depends(verify_jwt),
):
    """
    Connect a user's database:
    1. Introspect schema
    2. Create Backboard assistant + thread
    3. Send schema as first memory message
    4. Store everything in Supabase
    """
    # ── Detect DB type ────────────────────────────────────────────────────
    cs = body.connection_string
    # Mask password in logs: hide everything between :// and @
    cs_safe = cs.split("@")[-1] if "@" in cs else cs
    if cs.startswith("postgresql") or cs.startswith("postgres"):
        db_type = "postgresql"
    elif cs.startswith("mysql"):
        db_type = "mysql"
    elif cs.startswith("sqlite"):
        db_type = "sqlite"
    else:
        db_type = "unknown"
    logger.info("user=%s  db_type=%s  host/path=%s", user_id, db_type, cs_safe)

    # ── Schema introspection ──────────────────────────────────────────────
    logger.debug("user=%s  Starting schema introspection", user_id)
    try:
        schema_text = schema_service.introspect_schema(cs)
        table_count = schema_text.count("\nTable:")
        logger.info(
            "user=%s  Schema introspection complete — ~%d table(s) found, schema length=%d chars",
            user_id, table_count, len(schema_text),
        )
        logger.debug("user=%s  Schema preview (first 500 chars):\n%s", user_id, schema_text[:500])
    except ValueError as e:
        logger.error("user=%s  Schema introspection failed: %s", user_id, e)
        raise HTTPException(status_code=400, detail=str(e))

    # ── Backboard assistant + thread ──────────────────────────────────────
    logger.debug("user=%s  Creating Backboard assistant", user_id)
    try:
        assistant_id = await backboard.create_assistant(
            name=f"DB Copilot for user {user_id[:8]}"
        )
        logger.info("user=%s  Backboard assistant created — assistant_id=%s", user_id, assistant_id)

        logger.debug("user=%s  Creating Backboard thread for assistant=%s", user_id, assistant_id)
        thread_id = await backboard.create_thread(assistant_id)
        logger.info("user=%s  Backboard thread created — thread_id=%s", user_id, thread_id)
    except Exception as e:
        logger.exception("user=%s  Failed to create Backboard assistant/thread", user_id)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to initialize AI assistant: {str(e)}",
        )

    # ── Send schema as first memory message ───────────────────────────────
    logger.debug("user=%s  Sending schema to Backboard thread=%s", user_id, thread_id)
    try:
        schema_message = (
            "Here is the full database schema for this user's database. "
            "Use this as your primary reference when answering questions.\n\n"
            f"{schema_text}\n\n"
            "## Workflow reminder\n"
            "When a user asks a question:\n"
            "1. If you need to read or write data, reply with ONLY a single ```sql ... ``` block — no other text.\n"
            "2. The system will execute it and return the results (or rows-affected count) to you.\n"
            "3. Allowed statements: SELECT, INSERT, UPDATE. Forbidden: DROP, DELETE, TRUNCATE, ALTER.\n"
            "4. Repeat until done, then give your final answer in plain English with no SQL blocks."
        )
        reply_preview = await backboard.send_message(thread_id, schema_message, memory="Auto")
        logger.info(
            "user=%s  Schema sent to Backboard — AI reply preview: %.100s",
            user_id, reply_preview,
        )
    except Exception as e:
        logger.exception("user=%s  Failed to send schema to Backboard thread=%s", user_id, thread_id)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to send schema to AI assistant: {str(e)}",
        )

    # ── Persist to Supabase ───────────────────────────────────────────────
    logger.debug("user=%s  Upserting connection record to Supabase", user_id)
    try:
        supabase.table("connections").upsert(
            {
                "user_id": user_id,
                "connection_string": cs,
                "db_type": db_type,
                "backboard_assistant_id": assistant_id,
                "backboard_thread_id": thread_id,
            },
            on_conflict="user_id",
        ).execute()
        logger.info("user=%s  Connection record saved to Supabase", user_id)
    except Exception as e:
        logger.exception("user=%s  Failed to upsert connection record", user_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save connection record: {str(e)}",
        )

    logger.info("user=%s  Onboarding complete ✓", user_id)
    return ConnectResponse(success=True)
