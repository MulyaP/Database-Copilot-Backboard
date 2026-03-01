import logging
import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BACKBOARD_API_KEY = os.environ["BACKBOARD_API_KEY"]
BASE_URL = "https://app.backboard.io/api"


def _headers() -> dict:
    return {"X-API-Key": BACKBOARD_API_KEY}


async def create_assistant(name: str) -> str:
    """Create a new Backboard assistant and return its assistant_id."""
    url = f"{BASE_URL}/assistants"
    logger.debug("Backboard POST %s  name=%r", url, name)
    start = time.perf_counter()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json={
                    "name": name,
                    "system_prompt": (
                        "You are a Database Copilot. You help developers query and understand "
                        "their database using plain English.\n\n"
                        "## How to answer questions\n"
                        "You work in an agentic loop with the system:\n"
                        "1. When you need data, output EXACTLY ONE SQL query wrapped in a "
                        "```sql code block — nothing else in your message, no explanation.\n"
                        "2. The system will execute that query and return the results to you.\n"
                        "3. You can then run another query if needed, or give your final answer.\n"
                        "4. When you have enough data, reply in plain English with no SQL blocks.\n\n"
                        "## Rules\n"
                        "- One SQL statement per message when querying or writing.\n"
                        "- Allowed: SELECT, INSERT, UPDATE (including ... RETURNING ...).\n"
                        "- Forbidden: DROP, DELETE, TRUNCATE, ALTER — these will be blocked.\n"
                        "- Your final answer must contain no SQL blocks.\n"
                        "- Be concise and accurate."
                    ),
                },
                headers=_headers(),
                timeout=30.0,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "Backboard POST %s  status=%d  %.1fms",
                url, response.status_code, elapsed_ms,
            )
            if not response.is_success:
                logger.error(
                    "Backboard create_assistant failed  status=%d  body=%s",
                    response.status_code, response.text,
                )
            response.raise_for_status()
            data = response.json()
            logger.info("Backboard assistant created — assistant_id=%s", data["assistant_id"])
            return data["assistant_id"]
        except httpx.HTTPStatusError as e:
            logger.exception("Backboard HTTP error creating assistant: %s", e)
            raise
        except httpx.RequestError as e:
            logger.exception("Backboard network error creating assistant: %s", e)
            raise


async def create_thread(assistant_id: str) -> str:
    """Create a new thread for the given assistant and return its thread_id."""
    url = f"{BASE_URL}/assistants/{assistant_id}/threads"
    logger.debug("Backboard POST %s", url)
    start = time.perf_counter()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                headers=_headers(),
                timeout=30.0,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "Backboard POST %s  status=%d  %.1fms",
                url, response.status_code, elapsed_ms,
            )
            if not response.is_success:
                logger.error(
                    "Backboard create_thread failed  status=%d  body=%s",
                    response.status_code, response.text,
                )
            response.raise_for_status()
            data = response.json()
            logger.info(
                "Backboard thread created — assistant_id=%s  thread_id=%s",
                assistant_id, data["thread_id"],
            )
            return data["thread_id"]
        except httpx.HTTPStatusError as e:
            logger.exception("Backboard HTTP error creating thread: %s", e)
            raise
        except httpx.RequestError as e:
            logger.exception("Backboard network error creating thread: %s", e)
            raise


async def send_message(thread_id: str, content: str, memory: str = "Auto") -> str:
    """Send a message to a thread and return the assistant's reply text."""
    url = f"{BASE_URL}/threads/{thread_id}/messages"
    logger.debug(
        "Backboard POST %s  memory=%s  content length=%d chars",
        url, memory, len(content),
    )
    start = time.perf_counter()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                headers=_headers(),
                data={
                    "content": content,
                    "stream": "false",
                    "memory": memory,
                },
                timeout=120.0,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "Backboard POST %s  status=%d  %.1fms",
                url, response.status_code, elapsed_ms,
            )
            if not response.is_success:
                logger.error(
                    "Backboard send_message failed  thread=%s  status=%d  body=%s",
                    thread_id, response.status_code, response.text,
                )
            response.raise_for_status()
            data = response.json()
            reply = data["content"]
            logger.info(
                "Backboard reply received — thread=%s  reply length=%d chars",
                thread_id, len(reply),
            )
            logger.debug("Backboard full reply:\n%s", reply)
            return reply
        except httpx.HTTPStatusError as e:
            logger.exception("Backboard HTTP error sending message to thread=%s: %s", thread_id, e)
            raise
        except httpx.RequestError as e:
            logger.exception("Backboard network error sending message to thread=%s: %s", thread_id, e)
            raise
