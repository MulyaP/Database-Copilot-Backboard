import json
import logging
import os
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])

MODEL = "llama-3.3-70b-versatile"

# Tool definition passed to Groq on every request.
EXECUTE_SQL_TOOL = {
    "type": "function",
    "function": {
        "name": "execute_sql",
        "description": (
            "Execute a SQL statement against the user's database. "
            "Allowed: SELECT (including CTEs), INSERT, UPDATE (with optional RETURNING). "
            "Forbidden (blocked server-side): DROP, DELETE, TRUNCATE, ALTER, CREATE, REPLACE, "
            "MERGE, GRANT, REVOKE, EXEC, EXECUTE, CALL, LOAD, COPY, IMPORT, EXPORT, ATTACH, DETACH."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SQL statement to execute.",
                }
            },
            "required": ["sql"],
        },
    },
}


async def chat(messages: list[dict]) -> dict:
    """
    Send a list of messages to Groq and return the assistant message as a plain dict.

    The returned dict always has 'role': 'assistant'.
    When the model wants to call a tool it also has 'tool_calls': list[dict].
    When it gives a final text answer it has 'content': str (and no 'tool_calls').
    """
    logger.debug("Groq chat — %d message(s) in context", len(messages))
    response = await _client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=[EXECUTE_SQL_TOOL],
        tool_choice="auto",
        temperature=0,
    )
    choice = response.choices[0]
    msg = choice.message
    logger.debug(
        "Groq response — finish_reason=%s  tool_calls=%s",
        choice.finish_reason,
        len(msg.tool_calls) if msg.tool_calls else 0,
    )

    # Convert SDK object to a plain dict so callers don't import Groq types.
    result: dict = {"role": "assistant", "content": msg.content}
    if msg.tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return result
