"""Helpers for shelling out to the gws CLI."""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)


class GWSError(Exception):
    """Raised when a gws subprocess fails."""


def _run_gws(args: list[str]) -> str:
    """Run a gws command and return stdout."""
    cmd = ["gws", *args]
    logger.debug("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise GWSError(f"gws failed (rc={result.returncode}): {result.stderr.strip()}")
    return result.stdout


def gws_list_messages(query: str) -> list[dict]:
    """List message IDs matching a Gmail query, handling pagination."""
    all_messages: list[dict] = []
    page_token: str | None = None

    while True:
        params: dict = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            params["pageToken"] = page_token

        raw = _run_gws([
            "gmail", "users", "messages", "list",
            "--params", json.dumps(params),
        ])
        data = json.loads(raw)
        messages = data.get("messages", [])
        all_messages.extend(messages)
        logger.info("Fetched %d message IDs (total so far: %d)", len(messages), len(all_messages))

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return all_messages


def gws_get_message(msg_id: str) -> dict:
    """Fetch a single message by ID in full format."""
    raw = _run_gws([
        "gmail", "users", "messages", "get",
        "--params", json.dumps({"userId": "me", "id": msg_id, "format": "full"}),
    ])
    return json.loads(raw)


def gws_get_attachment(msg_id: str, attachment_id: str) -> bytes:
    """Download an attachment and return its raw bytes."""
    import base64

    raw = _run_gws([
        "gmail", "users", "messages", "attachments", "get",
        "--params", json.dumps({
            "userId": "me",
            "messageId": msg_id,
            "id": attachment_id,
        }),
    ])
    data = json.loads(raw)
    return base64.urlsafe_b64decode(data["data"])
