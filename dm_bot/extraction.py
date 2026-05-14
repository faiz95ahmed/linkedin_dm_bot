"""Data transfer objects and extractors for message extraction from LinkedIn accessibility tree.

This module provides Pydantic models for representing extracted data from LinkedIn's
accessibility tree before it is converted to storage models. These DTOs serve as
the bridge between the extraction layer and the storage layer.

It also provides extractor classes that parse accessibility tree snapshots to
extract structured data.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# System local timezone for converting LinkedIn's local-time displays to UTC
_LOCAL_TZ = datetime.now(timezone.utc).astimezone().tzinfo


def _local_to_utc(dt: datetime) -> datetime:
    """Convert a naive local-time datetime to a naive UTC datetime."""
    return dt.replace(tzinfo=_LOCAL_TZ).astimezone(timezone.utc).replace(tzinfo=None)


# =============================================================================
# Custom Exceptions
# =============================================================================


class ExtractionError(Exception):
    """Base exception for extraction errors."""

    pass


class ConversationNotFoundError(ExtractionError):
    """Raised when a conversation cannot be found in the inbox."""

    pass


# =============================================================================
# Data Transfer Objects
# =============================================================================


class ConversationPreview(BaseModel):
    """Preview data from inbox list item.

    Represents the summary information visible in the messaging inbox
    for a single conversation, before opening the full conversation view.

    Attributes:
        connection_name: Display name of the connection in the conversation
        last_message_snippet: Preview text of the last message, if available
        timestamp: Timestamp of the last message, if available
        thread_url: URL to the conversation thread, if available
    """

    connection_name: str
    last_message_snippet: str | None = None
    timestamp: datetime | None = None
    thread_url: str | None = None


class ConnectionInfo(BaseModel):
    """Connection data extracted from conversation header.

    Represents the connection profile information extracted from
    the conversation view header area.

    Attributes:
        display_name: The connection's display name
        linkedin_slug: Unique identifier from LinkedIn profile URL
        profile_url: Full URL to the connection's profile
    """

    display_name: str
    linkedin_slug: str | None = None
    profile_url: str | None = None


class ExtractedMessage(BaseModel):
    """Message data extracted from conversation view.

    Represents a single message extracted from the conversation
    accessibility tree, before being converted to a storage Message.

    Attributes:
        content: The message text content
        timestamp: When the message was sent
        direction: 'inbound' for received messages, 'outbound' for sent messages
        sender_name: Name of the sender, if available
    """

    content: str
    timestamp: datetime | None = None
    direction: Literal["inbound", "outbound"]
    sender_name: str | None = None


# =============================================================================
# Extractors
# =============================================================================


class InboxExtractor:
    """Extracts conversation previews from inbox accessibility tree.

    This class parses the accessibility tree snapshot from LinkedIn's messaging
    inbox to find and extract conversation preview information.

    The extractor traverses the tree looking for list items within a conversation
    list container, then parses each item to extract connection name, message
    snippet, and timestamp.
    """

    # Common ARIA roles for conversation list containers
    _LIST_ROLES = {"list", "listbox"}
    # Common ARIA roles for conversation items
    _ITEM_ROLES = {"listitem", "option"}
    # Patterns for identifying conversation list by name
    _CONVERSATION_LIST_PATTERNS = [
        re.compile(r"conversation", re.IGNORECASE),
        re.compile(r"message", re.IGNORECASE),
        re.compile(r"inbox", re.IGNORECASE),
    ]
    # Pattern for parsing relative timestamps like "Jan 15", "2h", "3d"
    _TIMESTAMP_PATTERNS = [
        # Relative words: "Today", "Yesterday"
        re.compile(r"^Today$", re.IGNORECASE),
        re.compile(r"^Yesterday$", re.IGNORECASE),
        # Full date: "Jan 15", "Dec 3"
        re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2})$"),
        # Hours ago: "2h", "12h"
        re.compile(r"^(\d+)h$"),
        # Days ago: "3d", "7d"
        re.compile(r"^(\d+)d$"),
        # Minutes ago: "5m", "30m"
        re.compile(r"^(\d+)m$"),
        # Weeks ago: "1w", "2w"
        re.compile(r"^(\d+)w$"),
        # Time: "3:45 PM", "10:30 AM"
        re.compile(r"^(\d{1,2}):(\d{2})\s*(AM|PM)$", re.IGNORECASE),
    ]

    def extract_previews(self, snapshot: dict[str, Any]) -> list[ConversationPreview]:
        """Parse inbox snapshot to find conversation list items.

        Traverses the accessibility tree to find the conversation list container,
        then parses each list item to extract preview information.

        Args:
            snapshot: Accessibility tree snapshot from page.accessibility.snapshot()

        Returns:
            List of ConversationPreview objects, one for each conversation found.
            Returns empty list if no conversations found or snapshot is empty.
        """
        if not snapshot:
            logger.warning("Empty accessibility tree snapshot provided")
            return []

        # Find the conversation list container
        conversation_list = self.find_conversation_list(snapshot)
        if conversation_list is None:
            logger.warning("Could not find conversation list in accessibility tree")
            return []

        # Extract children (list items)
        children = conversation_list.get("children", [])
        if not children:
            logger.debug("Conversation list has no children")
            return []

        # Parse each list item
        previews: list[ConversationPreview] = []
        for child in children:
            preview = self.parse_preview_item(child)
            if preview is not None:
                previews.append(preview)

        logger.info(f"Extracted {len(previews)} conversation previews")
        return previews

    def find_conversation_list(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        """Find the conversation list container in the tree.

        Performs a depth-first search of the accessibility tree to find a list
        element that appears to contain conversations.

        Args:
            snapshot: Accessibility tree snapshot or subtree node

        Returns:
            The list node containing conversations, or None if not found.
        """
        # Primary strategy: find a list whose items match LinkedIn's conversation
        # item pattern (listitem > link > region with name ending in " |").
        result = self._find_linkedin_conversation_list(snapshot)
        if result is not None:
            logger.debug("Found conversation list via LinkedIn item pattern")
            return result

        # Secondary: find an element named "Inbox" and return its list child.
        inbox_container = self._find_node_by_name(snapshot, r"^Inbox$")
        if inbox_container:
            for child in inbox_container.get("children", []):
                if child.get("role", "").lower() in self._LIST_ROLES:
                    logger.debug("Found conversation list via Inbox container")
                    return child

        # Fallback: generic recursive search
        return self._find_list_recursive(snapshot)

    def _find_linkedin_conversation_list(
        self, node: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Find a list that contains LinkedIn-style conversation items.

        LinkedIn conversation items have the pattern:
          listitem > link > region(name ends with " |") > p

        Args:
            node: Current node in the accessibility tree

        Returns:
            The list node if found, None otherwise.
        """
        role = node.get("role", "").lower()
        if role in self._LIST_ROLES:
            if self._has_linkedin_item_pattern(node):
                return node

        for child in node.get("children", []):
            result = self._find_linkedin_conversation_list(child)
            if result is not None:
                return result

        return None

    def _has_linkedin_item_pattern(self, list_node: dict[str, Any]) -> bool:
        """Check if a list's first item matches the LinkedIn conversation structure."""
        children = list_node.get("children", [])
        if not children:
            return False
        first_child = children[0]
        if first_child.get("role", "").lower() not in self._ITEM_ROLES:
            return False
        return self._has_name_pipe_suffix_descendant(first_child)

    def _has_name_pipe_suffix_descendant(self, node: dict[str, Any]) -> bool:
        """Return True if any descendant has a name containing ' | '."""
        if " | " in node.get("name", ""):
            return True
        for child in node.get("children", []):
            if self._has_name_pipe_suffix_descendant(child):
                return True
        return False

    def _find_node_by_name(
        self, node: dict[str, Any], pattern_str: str
    ) -> dict[str, Any] | None:
        """Find first node whose name matches pattern_str (case-insensitive)."""
        pattern = re.compile(pattern_str, re.IGNORECASE)
        return self._find_node_by_name_recursive(node, pattern)

    def _find_node_by_name_recursive(
        self, node: dict[str, Any], pattern: re.Pattern[str]
    ) -> dict[str, Any] | None:
        if pattern.search(node.get("name", "")):
            return node
        for child in node.get("children", []):
            result = self._find_node_by_name_recursive(child, pattern)
            if result is not None:
                return result
        return None

    def _find_list_recursive(self, node: dict[str, Any]) -> dict[str, Any] | None:
        """Recursively search for conversation list in the tree.

        Args:
            node: Current node in the accessibility tree

        Returns:
            The list node if found, None otherwise.
        """
        if not node:
            return None

        role = node.get("role", "").lower()
        name = node.get("name", "")

        # Check if this node is a list that might contain conversations
        if role in self._LIST_ROLES:
            # Check if the name suggests this is a conversation list
            if self._is_conversation_list(name, node):
                return node

        # Recursively search children
        children = node.get("children", [])
        for child in children:
            result = self._find_list_recursive(child)
            if result is not None:
                return result

        return None

    def _is_conversation_list(self, name: str, node: dict[str, Any]) -> bool:
        """Determine if a list node is likely a conversation list.

        Args:
            name: The accessible name of the node
            node: The node to check

        Returns:
            True if this appears to be a conversation list.
        """
        # Check if name matches conversation patterns
        for pattern in self._CONVERSATION_LIST_PATTERNS:
            if pattern.search(name):
                return True

        # Check if children look like conversation items
        children = node.get("children", [])
        if len(children) >= 1:
            # Check if first child has expected structure
            first_child = children[0]
            child_role = first_child.get("role", "").lower()
            if child_role in self._ITEM_ROLES:
                # Check if it has text content that looks like a conversation
                child_name = first_child.get("name", "")
                if child_name and len(child_name) > 0:
                    return True

        return False

    def parse_preview_item(self, node: dict[str, Any]) -> ConversationPreview | None:
        """Parse a single list item into ConversationPreview.

        Extracts connection name, message snippet, and timestamp from a
        conversation list item node.

        Args:
            node: A list item node from the accessibility tree

        Returns:
            ConversationPreview if parsing succeeds, None if the node
            doesn't appear to be a valid conversation item.
        """
        if not node:
            return None

        role = node.get("role", "").lower()

        # Verify this is a list item
        if role not in self._ITEM_ROLES:
            return None

        # Extract text content from the node
        connection_name = ""
        last_message_snippet: str | None = None
        timestamp: datetime | None = None
        thread_url: str | None = None

        # The accessible name often contains the connection name
        name = node.get("name", "")
        if name:
            # The name might be the full text or just the connection name
            connection_name = self._extract_connection_name(name, node)

        # If no connection name from accessible name, try children
        if not connection_name:
            connection_name = self._extract_connection_name_from_children(node)

        # If still no connection name, this isn't a valid conversation item
        if not connection_name:
            return None

        # Extract snippet and timestamp from children
        last_message_snippet = self._extract_snippet(node)
        timestamp = self._extract_timestamp(node)

        # Try to extract thread URL from any link in the node
        thread_url = self._extract_thread_url(node)

        return ConversationPreview(
            connection_name=connection_name,
            last_message_snippet=last_message_snippet,
            timestamp=timestamp,
            thread_url=thread_url,
        )

    def _extract_connection_name(
        self, name: str, node: dict[str, Any]
    ) -> str:
        """Extract connection name from accessible name.

        The accessible name might contain just the name, or it might contain
        the full preview text. This method attempts to extract just the name.

        Args:
            name: The accessible name of the node
            node: The node for additional context

        Returns:
            The extracted connection name, or empty string if not found.
        """
        if not name:
            return ""

        # Single-letter names are avatar initials, not connection names
        if len(name) <= 2:
            return ""

        # If the name is short (likely just the connection name), use it directly
        # LinkedIn names are typically under 100 characters
        if len(name) < 100:
            # Check if it looks like a name (not a timestamp or snippet)
            if not self._looks_like_timestamp(name):
                return name.strip()

        # If the name is longer, it might contain multiple pieces
        # Try to extract the first line or segment
        lines = name.split("\n")
        if lines:
            first_line = lines[0].strip()
            if first_line and not self._looks_like_timestamp(first_line):
                return first_line

        return name.strip()

    def _extract_connection_name_from_children(
        self, node: dict[str, Any]
    ) -> str:
        """Extract connection name from child nodes.

        Args:
            node: The parent node to search

        Returns:
            The connection name if found, empty string otherwise.
        """
        # Primary: LinkedIn inbox items encode names as "Name | JobTitle" in region
        # (section) element names. Split on " | " and take the first segment.
        name = self._find_name_pipe_prefix(node)
        if name:
            return name

        # Fallback: look for heading/link/text/statictext with non-timestamp name
        children = node.get("children", [])
        for child in children:
            child_role = child.get("role", "").lower()
            child_name = child.get("name", "")

            if child_role in {"heading", "link", "text", "statictext"}:
                if child_name and not self._looks_like_timestamp(child_name):
                    if len(child_name) < 100:
                        return child_name.strip()

            result = self._extract_connection_name_from_children(child)
            if result:
                return result

        return ""

    def _find_name_pipe_prefix(self, node: dict[str, Any]) -> str:
        """Extract the connection name from a 'Name | JobTitle' formatted node name.

        LinkedIn encodes conversation preview text as 'PersonName | JobTitle...'
        in region (section) element names. This finds the first node whose name
        contains ' | ' and returns just the part before the first ' | '.

        Args:
            node: Root node to search

        Returns:
            The name segment before ' | ', or empty string if not found.
        """
        name = node.get("name", "")
        if " | " in name:
            candidate = name.split(" | ")[0].strip()
            # Must be a plausible name: >2 chars and not a timestamp
            if len(candidate) > 2 and not self._looks_like_timestamp(candidate):
                return candidate
        for child in node.get("children", []):
            result = self._find_name_pipe_prefix(child)
            if result:
                return result
        return ""

    def _extract_snippet(self, node: dict[str, Any]) -> str | None:
        """Extract message snippet from node.

        Args:
            node: The conversation item node

        Returns:
            The message snippet if found, None otherwise.
        """
        texts: list[str] = []

        # Collect all text content from children
        self._collect_text_content(node, texts)

        # The snippet is usually the longest text that isn't the connection name
        # and isn't a timestamp
        for text in sorted(texts, key=len, reverse=True):
            if not self._looks_like_timestamp(text) and len(text) > 10:
                return text.strip()

        return None

    def _collect_text_content(
        self, node: dict[str, Any], texts: list[str]
    ) -> None:
        """Recursively collect text content from node and children.

        Args:
            node: Current node
            texts: List to append text content to
        """
        role = node.get("role", "").lower()
        name = node.get("name", "")

        if role in {"text", "statictext"} and name:
            texts.append(name)

        for child in node.get("children", []):
            self._collect_text_content(child, texts)

    def _extract_timestamp(self, node: dict[str, Any]) -> datetime | None:
        """Extract timestamp from node by searching all descendant node names.

        Our custom buildTree never produces text/statictext roles, so we walk
        the entire subtree looking for any node whose name matches a timestamp
        pattern (e.g. a <p> child with name "2d" or "Jan 3").

        Args:
            node: The conversation item node

        Returns:
            Parsed datetime if found, None otherwise.
        """
        return self._search_for_timestamp(node)

    def _search_for_timestamp(self, node: dict[str, Any]) -> datetime | None:
        """Recursively search all node names for a timestamp pattern.

        Args:
            node: Starting node

        Returns:
            Parsed datetime if a timestamp is found, None otherwise.
        """
        name = node.get("name", "").strip()
        if name and self._looks_like_timestamp(name):
            parsed = self._parse_timestamp(name)
            if parsed is not None:
                return parsed
        for child in node.get("children", []):
            result = self._search_for_timestamp(child)
            if result is not None:
                return result
        return None

    def _looks_like_timestamp(self, text: str) -> bool:
        """Check if text looks like a timestamp.

        Args:
            text: Text to check

        Returns:
            True if text appears to be a timestamp.
        """
        text = text.strip()
        if not text:
            return False

        for pattern in self._TIMESTAMP_PATTERNS:
            if pattern.match(text):
                return True

        return False

    def _parse_timestamp(self, text: str) -> datetime | None:
        """Parse timestamp text into datetime.

        Args:
            text: Timestamp text to parse

        Returns:
            Parsed datetime, or None if parsing fails.
        """
        text = text.strip()
        now = datetime.now()
        utc_now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Try each pattern
        for pattern in self._TIMESTAMP_PATTERNS:
            match = pattern.match(text)
            if not match:
                continue

            try:
                # Today
                if "Today" in pattern.pattern:

                    return _local_to_utc(datetime(now.year, now.month, now.day))

                # Yesterday
                if "Yesterday" in pattern.pattern:

                    yesterday = now - timedelta(days=1)
                    return _local_to_utc(datetime(yesterday.year, yesterday.month, yesterday.day))

                # Full date: "Jan 15"
                if pattern.pattern.startswith("^([A-Z]"):
                    month_str, day_str = match.groups()
                    month_map = {
                        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
                        "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
                        "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
                    }
                    month = month_map.get(month_str, 1)
                    day = int(day_str)
                    year = now.year
                    # If the date is in the future, assume last year
                    result = datetime(year, month, day)
                    if result > now:
                        result = datetime(year - 1, month, day)
                    return _local_to_utc(result)

                # Hours ago: "2h"
                elif "h$" in pattern.pattern:
                    hours = int(match.group(1))

                    return utc_now - timedelta(hours=hours)

                # Days ago: "3d"
                elif "d$" in pattern.pattern:
                    days = int(match.group(1))

                    return utc_now - timedelta(days=days)

                # Minutes ago: "5m"
                elif "m$" in pattern.pattern:
                    minutes = int(match.group(1))

                    return utc_now - timedelta(minutes=minutes)

                # Weeks ago: "1w"
                elif "w$" in pattern.pattern:
                    weeks = int(match.group(1))

                    return utc_now - timedelta(weeks=weeks)

                # Time: "3:45 PM"
                elif "AM|PM" in pattern.pattern:
                    hour = int(match.group(1))
                    minute = int(match.group(2))
                    ampm = match.group(3).upper()
                    if ampm == "PM" and hour != 12:
                        hour += 12
                    elif ampm == "AM" and hour == 12:
                        hour = 0
                    return _local_to_utc(datetime(now.year, now.month, now.day, hour, minute))

            except (ValueError, KeyError) as e:
                logger.debug(f"Failed to parse timestamp '{text}': {e}")
                continue

        return None

    def _extract_thread_url(self, node: dict[str, Any]) -> str | None:
        """Extract thread URL from node.

        Args:
            node: The conversation item node

        Returns:
            Thread URL if found, None otherwise.
        """
        # Look for link elements with href
        role = node.get("role", "").lower()

        if role == "link":
            # Check for URL in various attributes
            url = node.get("url") or node.get("href")
            if url and "messaging" in url.lower():
                return url

        # Recursively check children
        for child in node.get("children", []):
            result = self._extract_thread_url(child)
            if result:
                return result

        return None


class ConnectionExtractor:
    """Extracts connection info from conversation view.

    This class parses the accessibility tree snapshot from a LinkedIn conversation
    view to extract connection profile information from the header area.

    The extractor looks for header elements containing the connection's display name
    and profile link, then extracts the linkedin_slug from the URL.
    """

    # Common ARIA roles for header elements
    _HEADER_ROLES = {"heading", "banner", "header"}
    # Common ARIA roles for link elements
    _LINK_ROLES = {"link"}
    # Patterns for identifying conversation header by name
    _HEADER_PATTERNS = [
        re.compile(r"conversation", re.IGNORECASE),
        re.compile(r"message", re.IGNORECASE),
        re.compile(r"chat", re.IGNORECASE),
    ]
    # Pattern for extracting linkedin_slug from profile URL
    # Matches: /in/john-doe-123abc/ or /in/john-doe/
    _PROFILE_URL_PATTERN = re.compile(r"/in/([^/?]+)")
    # Pattern for extracting slug from thread URL
    # Matches: /messaging/thread/2-abc123/ or /messaging/thread/john-doe/
    _THREAD_URL_PATTERN = re.compile(r"/messaging/thread/(?:\d+-)?([^/?]+)")

    def extract_connection_info(
        self, snapshot: dict[str, Any], thread_url: str | None = None
    ) -> ConnectionInfo | None:
        """Extract connection details from conversation header.

        Traverses the accessibility tree to find the conversation header,
        then extracts the connection's display name and profile URL.
        Falls back to parsing thread_url for slug if not directly available.

        Args:
            snapshot: Accessibility tree snapshot from page.accessibility.snapshot()
            thread_url: Optional thread URL to use as fallback for slug extraction

        Returns:
            ConnectionInfo if extraction succeeds, None if the header
            cannot be found or doesn't contain valid connection info.
        """
        if not snapshot:
            logger.warning("Empty accessibility tree snapshot provided")
            return None

        # Try to find connection info from header
        display_name: str | None = None
        profile_url: str | None = None
        linkedin_slug: str | None = None

        # Primary: search for an /in/ profile link anywhere in the tree.
        # This finds both patterns LinkedIn uses:
        #   1. Conversation-details panel: link > div > dl > dt > heading
        #   2. Message sender attribution: link > span "Person Name"
        profile_link = self._find_connection_profile_link(snapshot)
        if profile_link:
            display_name = profile_link.get("name")
            profile_url = profile_link.get("url")

        # Second try: InMail profile card — the first li of the message ol
        # contains an avatar img + name div + headline, with no /in/ href on the links.
        if not display_name:
            display_name = self._find_profile_card_name(snapshot)

        # Fallback: search for conversation header/banner element
        if not display_name:
            header_info = self._find_header_info(snapshot)
            if header_info:
                display_name = header_info.get("name")
                profile_url = header_info.get("url")

        # If no display name found, try to find any prominent name
        if not display_name:
            display_name = self._find_prominent_name(snapshot)

        # If still no display name, we can't create valid ConnectionInfo
        if not display_name:
            logger.warning("Could not find connection display name in snapshot")
            return None

        # Clean display_name: the banner aria-label often ends with " |" (pipe with
        # no content after it) or contains "Name | Headline".  Extract just the name.
        display_name = display_name.strip()
        if display_name.endswith(" |"):
            display_name = display_name[:-2].strip()
        if " | " in display_name:
            display_name = display_name.split(" | ")[0].strip()

        # Extract slug from profile URL if available
        if profile_url:
            linkedin_slug = self.parse_slug_from_url(profile_url)

        # Fallback: try to extract slug from thread URL
        if not linkedin_slug and thread_url:
            linkedin_slug = self.parse_slug_from_url(thread_url)

        return ConnectionInfo(
            display_name=display_name,
            linkedin_slug=linkedin_slug,
            profile_url=profile_url,
        )

    def parse_slug_from_url(self, url: str) -> str | None:
        """Extract linkedin_slug from thread or profile URL.

        Parses various LinkedIn URL formats to extract the unique identifier
        (slug) for a connection.

        Args:
            url: LinkedIn URL (profile URL or thread URL)

        Returns:
            The extracted slug, or None if parsing fails.
        """
        if not url:
            return None

        # Try profile URL pattern first (/in/slug)
        match = self._PROFILE_URL_PATTERN.search(url)
        if match:
            slug = match.group(1)
            # Clean up the slug (remove trailing slashes, etc.)
            return slug.rstrip("/").strip()

        # Try thread URL pattern (/messaging/thread/slug)
        match = self._THREAD_URL_PATTERN.search(url)
        if match:
            slug = match.group(1)
            return slug.rstrip("/").strip()

        logger.debug(f"Could not extract slug from URL: {url}")
        return None

    def _find_header_info(
        self, node: dict[str, Any], depth: int = 0
    ) -> dict[str, Any] | None:
        """Recursively search for header info in the tree.

        Looks for header elements or links that contain connection information.

        Args:
            node: Current node in the accessibility tree
            depth: Current depth in the tree (for limiting search)

        Returns:
            Dict with 'name' and optionally 'url' if found, None otherwise.
        """
        if not node or depth > 10:  # Limit search depth
            return None

        role = node.get("role", "").lower()
        name = node.get("name", "")

        # Check if this is a header element with a name
        if role in self._HEADER_ROLES and name:
            # Prefer heading text within the banner — LinkedIn mobile banners
            # contain a heading with the full "Name | Headline" text, whereas
            # the banner's own aria-label is often truncated or ends with " |".
            heading_name = self._find_heading_name_pipe_prefix(node)
            if heading_name:
                link_info = self._find_profile_link(node)
                return {
                    "name": heading_name,
                    "url": link_info.get("url") if link_info else None,
                }
            # Look for a link child with profile URL
            link_info = self._find_profile_link(node)
            if link_info:
                return {
                    "name": link_info.get("name") or name,
                    "url": link_info.get("url"),
                }
            return {"name": name, "url": None}

        # Check if this is a link that looks like a profile link
        if role in self._LINK_ROLES:
            url = node.get("url") or node.get("href", "")
            if url and "/in/" in url:
                return {"name": name, "url": url}

        # Recursively search children
        children = node.get("children", [])
        for child in children:
            result = self._find_header_info(child, depth + 1)
            if result:
                return result

        return None

    def _find_connection_profile_link(
        self, node: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Find the primary profile link for the conversation partner.

        LinkedIn mobile conversation views contain a link whose:
          - href contains '/in/'
          - name is "Open <Name>'s profile"
          - children: div > list(dl) > term(dt) > heading  (the person's name)
                                     > definition(dd)       (their headline)

        This is more reliable than searching the banner, which only has a
        truncated aria-label.  We do a full-depth search with no limit.

        Returns:
            Dict with 'name' (str) and 'url' (str) if found, None otherwise.
        """
        role = node.get("role", "").lower()
        href = node.get("href", "")

        if role == "link" and href and "/in/" in href:
            # Extract name: prefer the heading inside the dl structure
            name = self._extract_name_from_profile_link(node)
            if not name:
                # Fall back: parse "Open X's profile" from the link's own name
                link_name = node.get("name", "")
                if link_name.startswith("Open ") and "'s profile" in link_name:
                    name = link_name[len("Open "):]
                    name = name[: name.index("'s profile")].strip()
            if name:
                return {"name": name, "url": href}

        for child in node.get("children", []):
            result = self._find_connection_profile_link(child)
            if result:
                return result

        return None

    def _find_profile_card_name(self, node: dict[str, Any]) -> str | None:
        """Find person name from an InMail profile card.

        LinkedIn InMail conversations show a profile card as the FIRST item in
        the message ol (before any date separators or messages).  The card has:
          ol > li(no name) > div > a[img] + div > a > div[name=Person] > span[name=Person]

        The <a> tags here have no /in/ href (JavaScript navigation), so
        _find_connection_profile_link misses them entirely.

        We detect the profile card li by: (a) it has no date-like name, and
        (b) it contains an img element (the avatar photo).
        """
        ol = self._find_ol_node(node)
        if not ol:
            return None
        lis = ol.get("children", [])
        if not lis:
            return None
        first_li = lis[0]
        # Date separator li elements carry a name like "Mar 2" or "Today"
        if first_li.get("name"):
            return None
        # A profile card always has an avatar image
        if not self._subtree_has_tag(first_li, "img"):
            return None
        return self._find_first_person_name_in_subtree(first_li)

    def _find_ol_node(self, node: dict[str, Any]) -> dict[str, Any] | None:
        """Find the first <ol> element (message list) in the tree."""
        if node.get("tag") == "ol":
            return node
        for child in node.get("children", []):
            result = self._find_ol_node(child)
            if result:
                return result
        return None

    def _subtree_has_tag(self, node: dict[str, Any], tag: str, depth: int = 0) -> bool:
        """Return True if any node in the subtree has the given HTML tag."""
        if depth > 6:
            return False
        if node.get("tag") == tag:
            return True
        return any(
            self._subtree_has_tag(c, tag, depth + 1) for c in node.get("children", [])
        )

    def _find_first_person_name_in_subtree(
        self, node: dict[str, Any], depth: int = 0
    ) -> str | None:
        """Return the first div/span name in the subtree that looks like a person name."""
        if depth > 8:
            return None
        role = node.get("role", "").lower()
        name = node.get("name", "").strip()
        if role in {"div", "span"} and name and self._is_plausible_person_name(name):
            return name
        for child in node.get("children", []):
            result = self._find_first_person_name_in_subtree(child, depth + 1)
            if result:
                return result
        return None

    def _extract_name_from_profile_link(self, link_node: dict[str, Any]) -> str:
        """Extract person name from a profile link's subtree.

        Tries two structural patterns LinkedIn uses:

        1. Heading pattern (conversation-details panel):
               link > div > list(dl) > term(dt) > heading → person name

        2. Span pattern (message sender attribution):
               link > span/div → person name as direct child text
               (the 2nd /in/ link in the message listitem has a span child
               whose text is just the person's name)
        """
        # Pattern 1: heading anywhere in subtree
        for child in link_node.get("children", []):
            result = self._find_first_heading(child)
            if result:
                return result

        # Pattern 2: direct span/div child with a clean person name
        for child in link_node.get("children", []):
            role = child.get("role", "").lower()
            if role in {"span", "div"}:
                name = child.get("name", "").strip()
                if self._is_plausible_person_name(name):
                    return name

        return ""

    def _is_plausible_person_name(self, text: str) -> bool:
        """Return True if text looks like a person or company name (not a URL or UI label)."""
        if not text or len(text) < 3 or len(text) > 80:
            return False
        if text.startswith("http") or text.startswith("/"):
            return False
        if text.lower().startswith(("open ", "view ", "see ")):
            return False
        # Must contain at least one letter
        return any(c.isalpha() for c in text)

    def _find_first_heading(self, node: dict[str, Any], depth: int = 0) -> str:
        if depth > 5:
            return ""
        if node.get("role", "").lower() == "heading":
            name = node.get("name", "").strip()
            if name and len(name) > 1:
                return name
        for child in node.get("children", []):
            result = self._find_first_heading(child, depth + 1)
            if result:
                return result
        return ""

    def _find_heading_name_pipe_prefix(self, node: dict[str, Any]) -> str:
        """Search node's subtree for a heading whose name contains ' | '.

        LinkedIn mobile conversation banners contain a heading element with
        the full "Name | Headline" text.  We return the segment before ' | '
        as the connection name.

        Returns:
            Name segment before ' | ', or empty string if not found.
        """
        role = node.get("role", "").lower()
        name = node.get("name", "")
        if role == "heading" and " | " in name:
            candidate = name.split(" | ")[0].strip()
            if len(candidate) > 2:
                return candidate
        for child in node.get("children", []):
            result = self._find_heading_name_pipe_prefix(child)
            if result:
                return result
        return ""

    def _find_profile_link(self, node: dict[str, Any]) -> dict[str, Any] | None:
        """Find a profile link within a node.

        Args:
            node: Node to search within

        Returns:
            Dict with 'name' and 'url' if found, None otherwise.
        """
        role = node.get("role", "").lower()
        name = node.get("name", "")

        if role in self._LINK_ROLES:
            url = node.get("url") or node.get("href", "")
            if url and "/in/" in url:
                return {"name": name, "url": url}

        # Search children
        for child in node.get("children", []):
            result = self._find_profile_link(child)
            if result:
                return result

        return None

    def _find_prominent_name(self, node: dict[str, Any], depth: int = 0) -> str | None:
        """Find a prominent name in the tree (fallback method).

        Looks for heading elements or other prominent text that might
        contain the connection name.

        Args:
            node: Current node in the accessibility tree
            depth: Current depth in the tree

        Returns:
            The name if found, None otherwise.
        """
        if not node or depth > 10:
            return None

        role = node.get("role", "").lower()
        name = node.get("name", "")

        # Headings are good candidates for connection names
        if role == "heading" and name:
            # Filter out generic headings
            if len(name) < 100 and not self._is_generic_heading(name):
                return name.strip()

        # Links with /in/ URLs often have the connection name
        if role == "link":
            url = node.get("url") or node.get("href", "")
            if url and "/in/" in url and name:
                return name.strip()

        # Search children
        for child in node.get("children", []):
            result = self._find_prominent_name(child, depth + 1)
            if result:
                return result

        return None

    def _is_generic_heading(self, text: str) -> bool:
        """Check if text is a generic heading (not a person's name).

        Args:
            text: Text to check

        Returns:
            True if text appears to be a generic heading.
        """
        generic_patterns = [
            re.compile(r"^message", re.IGNORECASE),
            re.compile(r"^conversation", re.IGNORECASE),
            re.compile(r"^chat", re.IGNORECASE),
            re.compile(r"^inbox", re.IGNORECASE),
            re.compile(r"^linkedin", re.IGNORECASE),
        ]
        for pattern in generic_patterns:
            if pattern.match(text):
                return True
        return False


class MessageExtractor:
    """Extracts messages from conversation accessibility tree.

    This class parses the accessibility tree snapshot from a LinkedIn conversation
    view to extract individual messages with their content, timestamp, and direction.

    The extractor traverses the tree looking for message elements, then parses each
    to extract the message content, timestamp, and whether it's inbound or outbound.
    Results are sorted by timestamp ascending.
    """

    # Common ARIA roles for message containers
    _CONTAINER_ROLES = {"list", "listbox", "log", "region", "div", "main"}
    # Common ARIA roles for message elements
    _MESSAGE_ROLES = {"listitem", "article", "group", "div"}
    # Patterns for identifying message container by name
    _MESSAGE_CONTAINER_PATTERNS = [
        re.compile(r"message", re.IGNORECASE),
        re.compile(r"conversation", re.IGNORECASE),
        re.compile(r"chat", re.IGNORECASE),
    ]
    # Patterns for parsing message timestamps
    _TIMESTAMP_PATTERNS = [
        # Time with AM/PM: "3:45 PM", "10:30 AM"
        re.compile(r"^(\d{1,2}):(\d{2})\s*(AM|PM)$", re.IGNORECASE),
        # 24h time: "12:35", "09:11" (LinkedIn shows time-only for today's messages)
        re.compile(r"^(\d{1,2}):(\d{2})$"),
        # Full date with time: "Jan 15, 3:45 PM"
        re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2}),?\s+(\d{1,2}):(\d{2})\s*(AM|PM)$", re.IGNORECASE),
        # Full date: "Jan 15", "Dec 3"
        re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2})$"),
        # ISO-like: "2024-01-15"
        re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"),
        # Hours ago: "2h", "12h"
        re.compile(r"^(\d+)h$"),
        # Days ago: "3d", "7d"
        re.compile(r"^(\d+)d$"),
        # Minutes ago: "5m", "30m"
        re.compile(r"^(\d+)m$"),
    ]
    # Patterns for identifying outbound messages
    _OUTBOUND_PATTERNS = [
        re.compile(r"outbound", re.IGNORECASE),
        re.compile(r"sent", re.IGNORECASE),
        re.compile(r"you", re.IGNORECASE),
        re.compile(r"me", re.IGNORECASE),
    ]

    def extract_messages(self, snapshot: dict[str, Any]) -> list[ExtractedMessage]:
        """Parse conversation snapshot to find all messages.

        Traverses the accessibility tree to find the message container,
        then parses each message element to extract content, timestamp,
        and direction.

        Args:
            snapshot: Accessibility tree snapshot from page.accessibility.snapshot()

        Returns:
            List of ExtractedMessage objects ordered by timestamp ascending.
            Returns empty list if no messages found or snapshot is empty.
        """
        if not snapshot:
            logger.warning("Empty accessibility tree snapshot provided")
            return []

        # Find the message container
        message_container = self.find_message_container(snapshot)
        if message_container is None:
            logger.warning("Could not find message container in accessibility tree")
            return []

        # Extract messages from container
        messages: list[ExtractedMessage] = []
        self._extract_messages_recursive(message_container, messages)

        if not messages:
            logger.debug("No messages found in container")
            return []

        # Sort by timestamp ascending
        messages.sort(key=lambda m: m.timestamp)

        logger.info(f"Extracted {len(messages)} messages")
        return messages

    def find_message_container(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        """Find the message list container in the tree.

        Performs a depth-first search of the accessibility tree to find a
        container element that appears to hold messages.

        Args:
            snapshot: Accessibility tree snapshot or subtree node

        Returns:
            The container node holding messages, or None if not found.
        """
        return self._find_container_recursive(snapshot)

    def _find_container_recursive(self, node: dict[str, Any]) -> dict[str, Any] | None:
        """Recursively search for message container in the tree.

        Args:
            node: Current node in the accessibility tree

        Returns:
            The container node if found, None otherwise.
        """
        if not node:
            return None

        role = node.get("role", "").lower()
        name = node.get("name", "")

        # Check if this node is a container that might hold messages
        if role in self._CONTAINER_ROLES:
            if self._is_message_container(name, node):
                return node

        # Recursively search children
        children = node.get("children", [])
        for child in children:
            result = self._find_container_recursive(child)
            if result is not None:
                return result

        return None

    def _is_message_container(self, name: str, node: dict[str, Any]) -> bool:
        """Determine if a container node is likely a message container.

        Args:
            name: The accessible name of the node
            node: The node to check

        Returns:
            True if this appears to be a message container.
        """
        # Check if name matches message container patterns
        for pattern in self._MESSAGE_CONTAINER_PATTERNS:
            if pattern.search(name):
                return True

        # Check if any child looks like a message item
        children = node.get("children", [])
        for child in children:
            child_role = child.get("role", "").lower()
            child_name = child.get("name", "")

            # Traditional message roles with non-empty names
            if child_role in {"listitem", "article", "group"}:
                if child_name:
                    return True

            # LinkedIn mobile: message div has "Content\n  \n  Date" name format
            if child_role == "div" and "\n" in child_name:
                parts = [p.strip() for p in child_name.split("\n") if p.strip()]
                if len(parts) >= 2 and self._looks_like_timestamp(parts[-1]):
                    return True

        return False

    def _extract_messages_recursive(
        self, node: dict[str, Any], messages: list[ExtractedMessage]
    ) -> None:
        """Recursively extract messages from a container node.

        Args:
            node: Current node in the accessibility tree
            messages: List to append extracted messages to
        """
        if not node:
            return

        role = node.get("role", "").lower()

        # Check if this node is a message element
        if role in self._MESSAGE_ROLES:
            message = self.parse_message_element(node)
            if message is not None:
                messages.append(message)
                return  # Don't recurse into message children

        # Recursively check children
        children = node.get("children", [])
        for child in children:
            self._extract_messages_recursive(child, messages)

    def parse_message_element(self, node: dict[str, Any]) -> ExtractedMessage | None:
        """Parse a single message element into ExtractedMessage.

        Extracts content, timestamp, and direction from a message node.

        Args:
            node: A message element node from the accessibility tree

        Returns:
            ExtractedMessage if parsing succeeds, None if the node
            doesn't appear to be a valid message.
        """
        if not node:
            return None

        role = node.get("role", "").lower()

        # Verify this is a message element
        if role not in self._MESSAGE_ROLES:
            return None

        # LinkedIn mobile: div elements encode messages as "Content\n  \n  Date"
        # Skip div nodes that don't have this multi-line pattern
        if role == "div":
            node_name = node.get("name", "")
            if "\n" not in node_name:
                return None
            parts = [p.strip() for p in node_name.split("\n") if p.strip()]
            if len(parts) < 2 or not self._looks_like_timestamp(parts[-1]):
                return None
            # Skip date/time separator divs: those where all parts are timestamps
            content_parts = [p for p in parts[:-1] if not self._looks_like_timestamp(p)]
            if not content_parts:
                return None

        # For listitem role: filter out date separators and profile cards
        if role == "listitem":
            node_name = node.get("name", "").strip()
            # Skip date separator listitems (name is purely a timestamp)
            if node_name and self._looks_like_timestamp(node_name):
                return None
            # Skip profile card listitems — they have an img in the subtree
            # but no actual message content (they're the sender's profile card
            # at the top of InMail conversations)
            if self._subtree_has_role(node, "img"):
                return None

        # Extract content
        content = self._extract_content(node)
        if not content:
            return None

        # Extract timestamp
        timestamp = self._extract_timestamp(node)
        if timestamp is None:
            # Use current time as fallback
            timestamp = datetime.now(timezone.utc).replace(tzinfo=None)

        # Determine direction
        direction = self.determine_direction(node)

        # Extract sender name if available
        sender_name = self._extract_sender_name(node)

        return ExtractedMessage(
            content=content,
            timestamp=timestamp,
            direction=direction,
            sender_name=sender_name,
        )

    def determine_direction(self, node: dict[str, Any]) -> Literal["inbound", "outbound"]:
        """Determine if message is inbound or outbound based on attributes.

        Examines the node's attributes, description, and structure to determine
        whether the message was sent by the user (outbound) or received (inbound).

        Args:
            node: The message element node

        Returns:
            'outbound' if the message was sent by the user, 'inbound' otherwise.
        """
        # Check description attribute
        description = node.get("description", "")
        if description:
            for pattern in self._OUTBOUND_PATTERNS:
                if pattern.search(description):
                    return "outbound"

        # Check name attribute
        name = node.get("name", "")
        if name:
            # Check for "You" or "Me" at the start
            if name.lower().startswith("you:") or name.lower().startswith("me:"):
                return "outbound"

        # Check class or other attributes that might indicate direction
        class_name = node.get("class", "")
        if class_name:
            for pattern in self._OUTBOUND_PATTERNS:
                if pattern.search(class_name):
                    return "outbound"

        # Check children for sender indicators
        children = node.get("children", [])
        for child in children:
            child_name = child.get("name", "")
            child_description = child.get("description", "")
            
            for pattern in self._OUTBOUND_PATTERNS:
                if pattern.search(child_name) or pattern.search(child_description):
                    return "outbound"

        # Default to inbound
        return "inbound"

    def _extract_content(self, node: dict[str, Any]) -> str:
        """Extract message content from node.

        Args:
            node: The message element node

        Returns:
            The message content text, or empty string if not found.
        """
        # First try the node's name attribute
        name = node.get("name", "")
        if name:
            # LinkedIn mobile: message divs have "Content\n  \n  Date" names
            if "\n" in name:
                parts = [p.strip() for p in name.split("\n") if p.strip()]
                if len(parts) >= 2 and self._looks_like_timestamp(parts[-1]):
                    # All parts except the last (timestamp) are content
                    content_text = " ".join(parts[:-1])
                    return self._clean_content(content_text)
            if not self._looks_like_timestamp(name):
                content = self._clean_content(name)
                if content:
                    return content

        # Try to find content in children
        texts: list[str] = []
        self._collect_text_content(node, texts)

        # Find the longest text that isn't a timestamp
        for text in sorted(texts, key=len, reverse=True):
            if not self._looks_like_timestamp(text) and len(text) > 0:
                return self._clean_content(text)

        return ""

    def _clean_content(self, text: str) -> str:
        """Clean message content by removing sender prefixes.

        Args:
            text: Raw message text

        Returns:
            Cleaned message content.
        """
        text = text.strip()
        
        # Remove common sender prefixes
        prefixes = ["You:", "Me:", "Sent:"]
        for prefix in prefixes:
            if text.lower().startswith(prefix.lower()):
                text = text[len(prefix):].strip()
                break

        return text

    def _collect_text_content(
        self, node: dict[str, Any], texts: list[str]
    ) -> None:
        """Recursively collect text content from node and children.

        Args:
            node: Current node
            texts: List to append text content to
        """
        role = node.get("role", "").lower()
        name = node.get("name", "")

        if role in {"text", "statictext"} and name:
            texts.append(name)

        for child in node.get("children", []):
            self._collect_text_content(child, texts)

    def _extract_timestamp(self, node: dict[str, Any]) -> datetime | None:
        """Extract timestamp from node.

        For div-role messages, LinkedIn mobile encodes the timestamp as the last
        part of a multi-line name ("Content\n  \n  Date").  For listitem-role
        messages (InMail), we fall back to a recursive subtree search.

        Args:
            node: The message element node

        Returns:
            Parsed datetime if found, None otherwise.
        """
        # LinkedIn mobile: div message names are "Content\n  \n  Date"
        name = node.get("name", "")
        if name and "\n" in name:
            parts = [p.strip() for p in name.split("\n") if p.strip()]
            if parts:
                parsed = self._parse_timestamp(parts[-1])
                if parsed is not None:
                    return parsed

        # Fallback: search all descendant node names for a timestamp
        return self._search_for_timestamp(node)

    def _search_for_timestamp(self, node: dict[str, Any]) -> datetime | None:
        """Recursively search all node names for a timestamp pattern."""
        name = node.get("name", "").strip()
        if name and self._looks_like_timestamp(name):
            parsed = self._parse_timestamp(name)
            if parsed is not None:
                return parsed
        for child in node.get("children", []):
            result = self._search_for_timestamp(child)
            if result is not None:
                return result
        return None

    def _subtree_has_role(self, node: dict[str, Any], target_role: str) -> bool:
        """Return True if any node in the subtree has the given role or tag."""
        if node.get("role", "").lower() == target_role or node.get("tag", "").lower() == target_role:
            return True
        for child in node.get("children", []):
            if self._subtree_has_role(child, target_role):
                return True
        return False

    def _looks_like_timestamp(self, text: str) -> bool:
        """Check if text looks like a timestamp.

        Args:
            text: Text to check

        Returns:
            True if text appears to be a timestamp.
        """
        text = text.strip()
        if not text:
            return False

        for pattern in self._TIMESTAMP_PATTERNS:
            if pattern.match(text):
                return True

        return False

    def _parse_timestamp(self, text: str) -> datetime | None:
        """Parse timestamp text into datetime.

        Args:
            text: Timestamp text to parse

        Returns:
            Parsed datetime, or None if parsing fails.
        """
        text = text.strip()
        now = datetime.now()
        utc_now = datetime.now(timezone.utc).replace(tzinfo=None)

        for pattern in self._TIMESTAMP_PATTERNS:
            match = pattern.match(text)
            if not match:
                continue

            try:
                # Time with AM/PM: "3:45 PM"
                if pattern.pattern.startswith(r"^(\d{1,2}):(\d{2})\s*(AM|PM)"):
                    hour = int(match.group(1))
                    minute = int(match.group(2))
                    ampm = match.group(3).upper()
                    if ampm == "PM" and hour != 12:
                        hour += 12
                    elif ampm == "AM" and hour == 12:
                        hour = 0
                    result = datetime(now.year, now.month, now.day, hour, minute)
                    if result > now:
                        result -= timedelta(days=1)
                    return _local_to_utc(result)

                # 24h time: "12:35"
                elif pattern.pattern == r"^(\d{1,2}):(\d{2})$":
                    hour = int(match.group(1))
                    minute = int(match.group(2))
                    result = datetime(now.year, now.month, now.day, hour, minute)
                    if result > now:
                        result -= timedelta(days=1)
                    return _local_to_utc(result)

                # Full date with time: "Jan 15, 3:45 PM"
                elif "([A-Z][a-z]{2})\\s+(\\d{1,2}),?\\s+(\\d{1,2}):(\\d{2})\\s*(AM|PM)" in pattern.pattern:
                    month_str = match.group(1)
                    day = int(match.group(2))
                    hour = int(match.group(3))
                    minute = int(match.group(4))
                    ampm = match.group(5).upper()

                    month_map = {
                        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
                        "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
                        "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
                    }
                    month = month_map.get(month_str, 1)

                    if ampm == "PM" and hour != 12:
                        hour += 12
                    elif ampm == "AM" and hour == 12:
                        hour = 0

                    year = now.year
                    result = datetime(year, month, day, hour, minute)
                    if result > now:
                        result = datetime(year - 1, month, day, hour, minute)
                    return _local_to_utc(result)

                # Full date: "Jan 15"
                elif pattern.pattern == r"^([A-Z][a-z]{2})\s+(\d{1,2})$":
                    month_str, day_str = match.groups()
                    month_map = {
                        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
                        "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
                        "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
                    }
                    month = month_map.get(month_str, 1)
                    day = int(day_str)
                    year = now.year
                    result = datetime(year, month, day)
                    if result > now:
                        result = datetime(year - 1, month, day)
                    return _local_to_utc(result)

                # ISO-like: "2024-01-15"
                elif pattern.pattern == r"^(\d{4})-(\d{2})-(\d{2})$":
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                    return _local_to_utc(datetime(year, month, day))

                # Hours ago: "2h"
                elif "h$" in pattern.pattern:
                    hours = int(match.group(1))

                    return utc_now - timedelta(hours=hours)

                # Days ago: "3d"
                elif "d$" in pattern.pattern:
                    days = int(match.group(1))

                    return utc_now - timedelta(days=days)

                # Minutes ago: "5m"
                elif "m$" in pattern.pattern:
                    minutes = int(match.group(1))

                    return utc_now - timedelta(minutes=minutes)

            except (ValueError, KeyError) as e:
                logger.debug(f"Failed to parse timestamp '{text}': {e}")
                continue

        return None

    def _extract_sender_name(self, node: dict[str, Any]) -> str | None:
        """Extract sender name from node if available.

        Args:
            node: The message element node

        Returns:
            Sender name if found, None otherwise.
        """
        # Check for sender in children
        children = node.get("children", [])
        for child in children:
            child_role = child.get("role", "").lower()
            child_name = child.get("name", "")

            # Look for heading or link that might contain sender name
            if child_role in {"heading", "link"} and child_name:
                # Skip if it looks like a timestamp
                if not self._looks_like_timestamp(child_name):
                    return child_name.strip()

        # Check the node's name for sender prefix
        name = node.get("name", "")
        if ":" in name:
            parts = name.split(":", 1)
            sender = parts[0].strip()
            if sender and not self._looks_like_timestamp(sender):
                return sender

        return None


# =============================================================================
# Sync Engine
# =============================================================================


class SyncResult(BaseModel):
    """Result of a sync operation.

    Attributes:
        conversations_processed: Number of conversations synced
        messages_stored: Number of new messages stored
        messages_skipped: Number of messages skipped (already existed)
        errors: List of error messages encountered during sync
    """

    conversations_processed: int
    messages_stored: int
    messages_skipped: int
    errors: list[str]


class SyncEngine:
    """Orchestrates conversation sync workflow.

    This class coordinates the extraction of conversations and messages from
    LinkedIn's accessibility tree and persists them to the database using
    the storage repositories.

    The sync engine handles:
    - Extracting conversation previews from the inbox
    - Opening individual conversations to extract messages
    - Creating/updating Connection, Conversation, and Message records
    - Incremental sync based on timestamps
    - Scrolling to load older messages

    Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 7.1, 7.2, 7.3, 7.4
    """

    def __init__(
        self,
        page: Any,  # playwright.async_api.Page
        db: Any,  # DatabaseManager
        rate_limiter: Any,  # RateLimiter
        notifier: Any,  # NotificationService
    ) -> None:
        """Initialize SyncEngine with dependencies.

        Args:
            page: Playwright page object for browser interaction
            db: DatabaseManager instance for database operations
            rate_limiter: RateLimiter for human-like delays
            notifier: NotificationService for alerts
        """
        self._page = page
        self._db = db
        self._rate_limiter = rate_limiter
        self._notifier = notifier

        # Initialize extractors
        self._inbox_extractor = InboxExtractor()
        self._connection_extractor = ConnectionExtractor()
        self._message_extractor = MessageExtractor()

        # Initialize repositories (lazy import to avoid circular deps)
        from dm_bot.storage import (
            AttachmentRepository,
            ConnectionRepository,
            ConversationRepository,
            MessageRepository,
        )

        self._connection_repo = ConnectionRepository(db)
        self._conversation_repo = ConversationRepository(db)
        self._message_repo = MessageRepository(db)
        self._attachment_repo = AttachmentRepository(db)

    async def _get_accessibility_snapshot(self) -> dict[str, Any] | None:
        """Return the page accessibility tree as a dict.

        page.accessibility was removed in Playwright 1.40+. This method
        reconstructs the tree from the DOM using page.evaluate(), mirroring
        the same structure (role, name, children) that the extractor classes
        expect.
        """
        return await self._page.evaluate(
            """() => {
                const IMPLICIT_ROLES = {
                    'a': 'link', 'button': 'button', 'summary': 'button',
                    'ul': 'list', 'ol': 'list', 'menu': 'list',
                    'li': 'listitem',
                    'dl': 'list', 'dt': 'term', 'dd': 'definition',
                    'select': 'listbox', 'datalist': 'listbox',
                    'option': 'option',
                    'nav': 'navigation', 'main': 'main', 'footer': 'contentinfo',
                    'header': 'banner', 'aside': 'complementary',
                    'article': 'article', 'section': 'region',
                    'form': 'form', 'dialog': 'dialog',
                    'table': 'table', 'tr': 'row', 'td': 'cell',
                    'th': 'columnheader', 'tbody': 'rowgroup',
                    'thead': 'rowgroup', 'tfoot': 'rowgroup',
                    'h1': 'heading', 'h2': 'heading', 'h3': 'heading',
                    'h4': 'heading', 'h5': 'heading', 'h6': 'heading',
                    'img': 'img', 'input': 'textbox', 'textarea': 'textbox',
                    'hr': 'separator', 'progress': 'progressbar',
                };
                function buildTree(el) {
                    const tag = el.tagName.toLowerCase();
                    const role = el.getAttribute('role') || IMPLICIT_ROLES[tag] || tag;
                    const name = (
                        el.getAttribute('aria-label') ||
                        el.getAttribute('title') ||
                        el.textContent?.substring(0, 2000) || ''
                    ).trim();
                    const node = { role, name, tag };
                    // Include href for link elements so profile URLs are extractable
                    if (tag === 'a') {
                        const href = el.getAttribute('href');
                        if (href) node.href = href;
                    }
                    const ariaAttrs = {};
                    for (const attr of el.attributes) {
                        if (attr.name.startsWith('aria-')) {
                            ariaAttrs[attr.name] = attr.value;
                        }
                    }
                    if (Object.keys(ariaAttrs).length > 0) node.aria = ariaAttrs;
                    const children = Array.from(el.children).map(buildTree);
                    if (children.length > 0) node.children = children;
                    return node;
                }
                return buildTree(document.body);
            }"""
        )

    async def _enrich_with_thread_urls(
        self, previews: list[ConversationPreview]
    ) -> None:
        """Fetch conversation thread URLs from the DOM and assign to previews.

        The Playwright accessibility snapshot does not include href attributes,
        so we query the DOM directly to get the link for each conversation item.
        """
        try:
            hrefs: list[str] = await self._page.evaluate(
                """() => {
                    const links = document.querySelectorAll('ul li a');
                    return Array.from(links)
                        .map(a => a.href)
                        .filter(href => href.includes('/messaging/'));
                }"""
            )
            for i, preview in enumerate(previews):
                if i < len(hrefs):
                    preview.thread_url = hrefs[i]
            logger.info(f"Enriched {min(len(previews), len(hrefs))} previews with thread URLs")
        except Exception as e:
            logger.warning(f"Could not fetch thread URLs from DOM: {e}")

    def _safe_callback(
        self,
        callback: Any,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Safely invoke progress callback, catching any exceptions.

        Ensures callback failures don't break the sync process.

        Args:
            callback: Optional callback function
            event_type: Type of event (e.g., "conversation_start")
            data: Event data dictionary
        """
        if callback is None:
            return

        try:
            callback(event_type, data)
        except Exception as e:
            logger.warning(f"Progress callback failed for {event_type}: {e}")

    async def sync_conversations(
        self,
        since: datetime | None = None,
        limit: int = 50,
        progress_callback: Any = None,  # Callable[[str, dict[str, Any]], None] | None
        skip_triaged: bool = False,
    ) -> SyncResult:
        """Sync conversations from LinkedIn to database.

        Extracts conversation previews from the inbox, then syncs each
        conversation's messages to the database. Supports incremental
        sync based on timestamps and limiting the number of conversations.

        Args:
            since: Optional datetime to filter conversations with
                   activity after this date (Requirement 7.1)
            limit: Maximum number of conversations to process (Requirement 7.2)
            progress_callback: Optional callback for progress reporting.
                             Called with (event_type: str, data: dict[str, Any])
                             Event types: "conversation_start", "messages_extracted",
                             "messages_stored" (Requirement 3.1, 3.2, 3.3)

        Returns:
            SyncResult with counts of processed items and any errors

        Requirements:
            - 5.1: Create or update Connection record
            - 5.2: Create or update Conversation record
            - 5.3: Store messages with deduplication
            - 5.4: Update last_synced_at timestamp
            - 7.1: Filter by --since date parameter
            - 7.2: Respect --limit parameter
            - 7.3: Skip conversations where last_message_at <= last_synced_at
            - 7.4: Process in order of most recent activity first
            - 3.1: Report conversation start with name and progress
            - 3.2: Report messages extracted count
            - 3.3: Report messages stored (new vs skipped)
        """
        result = SyncResult(
            conversations_processed=0,
            messages_stored=0,
            messages_skipped=0,
            errors=[],
        )

        try:
            # Get accessibility snapshot of inbox
            snapshot = await self._get_accessibility_snapshot()
            if not snapshot:
                logger.warning("Empty accessibility snapshot from inbox")
                return result

            # Extract conversation previews
            previews = self._inbox_extractor.extract_previews(snapshot)
            if not previews:
                logger.info("No conversations found in inbox")
                return result

            logger.info(f"Found {len(previews)} conversations in inbox")

            # Enrich previews with thread URLs from DOM (not in accessibility tree)
            await self._enrich_with_thread_urls(previews)

            # Filter and sort previews for incremental sync
            previews = self._filter_previews_for_sync(previews, since)

            # Sort by timestamp descending (most recent first) - Requirement 7.4
            previews.sort(
                key=lambda p: p.timestamp or datetime.min,
                reverse=True,
            )

            # Apply limit - Requirement 7.2
            previews = previews[:limit]

            logger.info(f"Processing {len(previews)} conversations after filtering")

            # Sync each conversation
            total_conversations = len(previews)
            for index, preview in enumerate(previews, start=1):
                try:
                    # Report conversation start - Requirement 3.1
                    self._safe_callback(
                        progress_callback,
                        "conversation_start",
                        {
                            "index": index,
                            "total": total_conversations,
                            "name": preview.connection_name,
                        },
                    )

                    await self._rate_limiter.delay_for_conversation()
                    
                    # Check if this conversation is already triaged with no new messages
                    if preview.thread_url:
                        existing = self._conversation_repo.get_by_thread_url(
                            preview.thread_url
                        )
                        if (
                            existing
                            and existing.triaged_at is not None
                            and existing.last_message_at is not None
                            and existing.last_message_at <= existing.triaged_at
                        ):
                            if skip_triaged:
                                logger.info(
                                    f"Conversation '{preview.connection_name}' already triaged; skipping."
                                )
                                continue
                            logger.info(
                                f"Conversation '{preview.connection_name}' already triaged; stopping early."
                            )
                            break

                    stored, skipped, extracted_count = await self.sync_single_conversation(
                        preview, progress_callback
                    )
                    result.conversations_processed += 1
                    result.messages_stored += stored
                    result.messages_skipped += skipped

                except Exception as e:
                    error_msg = f"Error syncing conversation '{preview.connection_name}': {e}"
                    logger.error(error_msg, exc_info=True)
                    result.errors.append(error_msg)
                    continue

        except Exception as e:
            error_msg = f"Error during sync: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)

        logger.info(
            f"Sync complete: {result.conversations_processed} conversations, "
            f"{result.messages_stored} new messages, "
            f"{result.messages_skipped} skipped"
        )
        return result

    def _filter_previews_for_sync(
        self,
        previews: list[ConversationPreview],
        since: datetime | None,
    ) -> list[ConversationPreview]:
        """Filter previews based on sync criteria.

        Args:
            previews: List of conversation previews to filter
            since: Optional datetime to filter by activity date

        Returns:
            Filtered list of previews

        Requirements:
            - 7.1: Filter by --since date parameter
            - 7.3: Skip conversations where last_message_at <= last_synced_at
        """
        filtered: list[ConversationPreview] = []

        for preview in previews:
            # Filter by since date - Requirement 7.1
            if since is not None and preview.timestamp is not None:
                if preview.timestamp < since:
                    logger.debug(
                        f"Skipping '{preview.connection_name}': "
                        f"timestamp {preview.timestamp} < since {since}"
                    )
                    continue

            # Check if conversation needs sync - Requirement 7.3
            # This requires looking up existing conversation in DB
            if preview.thread_url:
                slug = self._connection_extractor.parse_slug_from_url(preview.thread_url)
                if slug:
                    existing_conn = self._connection_repo.get_by_slug(slug)
                    if existing_conn and existing_conn.id:
                        existing_conv = self._conversation_repo.get_by_connection_id(
                            existing_conn.id
                        )
                        if existing_conv:
                            # Skip if already synced and no new messages
                            if (
                                existing_conv.last_synced_at is not None
                                and existing_conv.last_message_at is not None
                                and existing_conv.last_message_at <= existing_conv.last_synced_at
                            ):
                                logger.debug(
                                    f"Skipping '{preview.connection_name}': "
                                    f"already synced"
                                )
                                continue

            filtered.append(preview)

        return filtered

    async def sync_single_conversation(
        self,
        preview: ConversationPreview,
        progress_callback: Any = None,
    ) -> tuple[int, int, int]:
        """Open and sync a single conversation.

        Navigates to the conversation, extracts connection info and messages,
        and persists them to the database.

        Args:
            preview: ConversationPreview from inbox extraction
            progress_callback: Optional callback for progress reporting

        Returns:
            Tuple of (messages_stored, messages_skipped, messages_extracted)

        Raises:
            ExtractionError: If extraction fails
            StorageError: If database operations fail

        Requirements:
            - 5.1: Create or update Connection record
            - 5.2: Create or update Conversation record
            - 5.3: Store messages with deduplication
            - 5.4: Update last_synced_at timestamp
            - 3.2: Report messages extracted count
            - 3.3: Report messages stored (new vs skipped)
        """
        from dm_bot.storage import Connection, Conversation, Message

        logger.info(f"Syncing conversation with '{preview.connection_name}'")

        messages_stored = 0
        messages_skipped = 0

        # Navigate to conversation if we have a thread URL.
        if preview.thread_url:
            await self._page.goto(preview.thread_url)
            await self._rate_limiter.delay_after_page_load()
            # If redirected to login, fill credentials on the current page.
            # LinkedIn's uas/login page pre-fills the email and only needs a password.
            if "/login" in self._page.url or "/uas/login" in self._page.url:
                logger.warning("Thread URL redirected to login page; filling credentials")
                from dm_bot.config import LI_USER, LI_PASS
                try:
                    # Fill email if the field is present and editable
                    email_field = await self._page.query_selector(
                        'input[type="email"], input[name="session_key"], '
                        'input[autocomplete="username"]'
                    )
                    if email_field and await email_field.is_visible():
                        await email_field.fill(LI_USER or "")
                        await asyncio.sleep(0.5)
                    # Click Continue if present (two-step flow)
                    try:
                        cont = await self._page.wait_for_selector(
                            'button[type="submit"]:not([data-id="sign-in-form__submit-btn"])',
                            timeout=1500,
                        )
                        if cont:
                            await cont.click()
                            await asyncio.sleep(2)
                    except Exception:
                        pass
                    # Fill password
                    pwd_field = await self._page.wait_for_selector(
                        'input[type="password"]', timeout=5000
                    )
                    await pwd_field.fill(LI_PASS or "")
                    await asyncio.sleep(0.5)
                    # Click Sign in
                    sign_in = await self._page.wait_for_selector(
                        'button[type="submit"], button[data-id="sign-in-form__submit-btn"]',
                        timeout=3000,
                    )
                    await sign_in.click()
                    await asyncio.sleep(3)
                    if "/login" in self._page.url:
                        raise ExtractionError("Re-login failed; please log in manually and retry")
                    logger.info("Re-login successful, re-navigating to thread")
                    await self._page.goto(preview.thread_url)
                    await self._rate_limiter.delay_after_page_load()
                except ExtractionError:
                    raise
                except Exception as e:
                    raise ExtractionError(f"Re-login error: {e}") from e

        # Wait for the message thread to render before snapshotting.
        # LinkedIn's SPA may render Layout A (msg-s-message-list__event) or
        # Layout B (member-message) depending on navigation context.
        try:
            await self._page.wait_for_selector(
                "li.msg-s-message-list__event, li.member-message",
                timeout=20000,
            )
            logger.debug("Message thread loaded")
        except Exception:
            logger.debug("Timed out waiting for thread lis; proceeding anyway")

        # Log current URL for debugging navigation issues
        current_url = self._page.url
        logger.info(f"Page URL before snapshot: {current_url}")

        # Scroll up to load all older messages so date separators are present in the DOM.
        # We stop when the li count stops growing (reached the top) or after max_scrolls.
        await self._scroll_conversation_to_top(max_scrolls=30)

        # Get the accessibility tree AND DOM messages in a single evaluate call
        # to avoid a race condition where Ember.js re-renders between two separate calls.
        combined = await self._page.evaluate("""
            () => {
                // ---- buildTree (accessibility snapshot) ----
                const IMPLICIT_ROLES = {
                    'a': 'link', 'button': 'button', 'summary': 'button',
                    'ul': 'list', 'ol': 'list', 'menu': 'list',
                    'li': 'listitem',
                    'dl': 'list', 'dt': 'term', 'dd': 'definition',
                    'select': 'listbox', 'datalist': 'listbox',
                    'option': 'option',
                    'nav': 'navigation', 'main': 'main', 'footer': 'contentinfo',
                    'header': 'banner', 'aside': 'complementary',
                    'article': 'article', 'section': 'region',
                    'form': 'form', 'dialog': 'dialog',
                    'table': 'table', 'tr': 'row', 'td': 'cell',
                    'th': 'columnheader', 'tbody': 'rowgroup',
                    'thead': 'rowgroup', 'tfoot': 'rowgroup',
                    'h1': 'heading', 'h2': 'heading', 'h3': 'heading',
                    'h4': 'heading', 'h5': 'heading', 'h6': 'heading',
                    'img': 'img', 'input': 'textbox', 'textarea': 'textbox',
                    'hr': 'separator', 'progress': 'progressbar',
                };
                function buildTree(el) {
                    const tag = el.tagName.toLowerCase();
                    const role = el.getAttribute('role') || IMPLICIT_ROLES[tag] || tag;
                    const name = (
                        el.getAttribute('aria-label') ||
                        el.getAttribute('title') ||
                        el.textContent?.substring(0, 2000) || ''
                    ).trim();
                    const node = { role, name, tag };
                    if (tag === 'a') {
                        const href = el.getAttribute('href');
                        if (href) node.href = href;
                    }
                    const ariaAttrs = {};
                    for (const attr of el.attributes) {
                        if (attr.name.startsWith('aria-')) {
                            ariaAttrs[attr.name] = attr.value;
                        }
                    }
                    if (Object.keys(ariaAttrs).length > 0) node.aria = ariaAttrs;
                    const children = Array.from(el.children).map(buildTree);
                    if (children.length > 0) node.children = children;
                    return node;
                }
                const tree = buildTree(document.body);

                // ---- DOM message extraction ----
                // Layout A: old LinkedIn style with explicit sender/timestamp elements
                function extractLayoutA() {
                    const lis = document.querySelectorAll('li.msg-s-message-list__event');
                    if (!lis.length) return null;
                    let currentDate = '';
                    const messages = [];
                    for (const li of lis) {
                        const dateEl = li.querySelector('time.msg-s-message-list__time-heading');
                        if (dateEl) currentDate = (dateEl.textContent || '').trim();
                        const senderEl  = li.querySelector('.msg-s-message-group__name');
                        const timeEl    = li.querySelector('time.msg-s-message-group__timestamp');
                        const bodyEl    = li.querySelector('p.msg-s-event-listitem__body');
                        const subjectEl = li.querySelector('h3.msg-s-event-listitem__subject');
                        const sender  = (senderEl?.textContent  || '').trim();
                        const time    = (timeEl?.textContent    || '').trim();
                        let   body    = (bodyEl?.textContent    || '').trim();
                        const subject = (subjectEl?.textContent || '').trim();
                        if (!body && !subject) continue;
                        if (subject) body = subject + '\\n' + body;
                        const attachLinksA = Array.from(
                            li.querySelectorAll('a[aria-label]')
                        ).filter(a =>
                            (a.getAttribute('aria-label') || '').toLowerCase().startsWith('download')
                        );
                        const attachmentsA = attachLinksA.map(a => {
                            const label = a.getAttribute('aria-label') || '';
                            const href = a.href || '';
                            const leafTexts = Array.from(a.querySelectorAll('div'))
                                .filter(d => d.childElementCount === 0)
                                .map(d => d.textContent.trim())
                                .filter(t => t.length > 4 && !/^\\d+$/.test(t) &&
                                    !['KB','MB','GB','Download'].includes(t));
                            const filename = leafTexts.sort((x, y) => y.length - x.length)[0] || label;
                            return { href, label, filename };
                        });
                        const _liNavPathsA = ['/in/', '/mwlite/messaging', '/mynetwork',
                                              '/jobs', '/feed', 'linkedinmobileapp.com'];
                        const linksA = Array.from(li.querySelectorAll('a[href]'))
                            .filter(la => {
                                const h = la.href || '';
                                if (!h || (!h.startsWith('http://') && !h.startsWith('https://'))) return false;
                                if (_liNavPathsA.some(p => h.includes(p))) return false;
                                if ((la.getAttribute('aria-label') || '').toLowerCase().startsWith('download')) return false;
                                return true;
                            })
                            .map(la => la.href);
                        messages.push({ sender, time, date: currentDate, body,
                                        isSelf: null, attachments: attachmentsA, links: linksA });
                    }
                    return messages.length ? messages : null;
                }

                // Layout B: legacy mobile LinkedIn style with li.member-message
                // li.member-message.self = sent by viewer (outbound)
                // li.member-message (no .self) = received (inbound)
                // Timestamp-only lis (body = "HH:MM") are paired with preceding message.
                function extractLayoutB() {
                    const memberLis = document.querySelectorAll('li.member-message');
                    if (!memberLis.length) return null;

                    // Collect raw items in DOM order
                    let currentDate = '';
                    const raw = [];

                    // Walk ALL lis to capture date separators and message lis in order
                    const allLis = document.querySelectorAll('li');
                    for (const li of allLis) {
                        const cls = (typeof li.className === 'string') ? li.className : '';

                        if (!cls.includes('member-message')) {
                            // Try to detect a date separator
                            const text = (li.textContent || '').trim();
                            // ISO date from <time datetime="YYYY-MM-DD..."> — most reliable
                            const timeEl = li.querySelector('time[datetime]');
                            if (timeEl) {
                                const dt = timeEl.getAttribute('datetime') || '';
                                if (/^\\d{4}-\\d{2}-\\d{2}/.test(dt)) {
                                    currentDate = dt;
                                    continue;
                                }
                            }
                            // "Mar 20, 2025" or "Jul 4, 2024" — month day year
                            if (/^[A-Z][a-z]{2}\\s+\\d{1,2},?\\s*\\d{4}$/.test(text)) {
                                currentDate = text; continue;
                            }
                            // "Mar 20" — month day, current year implied
                            if (/^[A-Z][a-z]{2}\\s+\\d{1,2}$/.test(text)) {
                                currentDate = text; continue;
                            }
                            // Day of week: "Monday" … "Sunday" — within last 6 days
                            if (/^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$/.test(text)) {
                                currentDate = text; continue;
                            }
                            // "Today" / "Yesterday"
                            if (/^(Today|Yesterday)$/i.test(text)) {
                                currentDate = text; continue;
                            }
                            continue;
                        }

                        const isSelf = cls.includes('self');
                        // Get body: prefer <p> element, fallback to li text
                        const bodyEl = li.querySelector('p');
                        const body = (bodyEl
                            ? (bodyEl.textContent || '')
                            : (li.textContent || '')
                        ).trim();

                        // Extract attachment download links within this li
                        const attachLinks = Array.from(
                            li.querySelectorAll('a[aria-label]')
                        ).filter(a =>
                            (a.getAttribute('aria-label') || '').toLowerCase().startsWith('download')
                        );
                        const attachments = attachLinks.map(a => {
                            const label = a.getAttribute('aria-label') || '';
                            const href = a.href || '';
                            // Pick the longest leaf-div text as filename (skips badge/size/icon text)
                            const leafTexts = Array.from(a.querySelectorAll('div'))
                                .filter(d => d.childElementCount === 0)
                                .map(d => d.textContent.trim())
                                .filter(t => t.length > 4 && !/^\\d+$/.test(t) &&
                                    !['KB','MB','GB','Download'].includes(t));
                            const filename = leafTexts.sort((x, y) => y.length - x.length)[0] || label;
                            return { href, label, filename };
                        });

                        // Extract outbound link hrefs (excludes LinkedIn internal nav)
                        const _liNavPaths = ['/in/', '/mwlite/messaging', '/mynetwork',
                                             '/jobs', '/feed', 'linkedinmobileapp.com'];
                        const links = Array.from(li.querySelectorAll('a[href]'))
                            .filter(la => {
                                const h = la.href || '';
                                if (!h || (!h.startsWith('http://') && !h.startsWith('https://'))) return false;
                                if (_liNavPaths.some(p => h.includes(p))) return false;
                                // Exclude attachment download links (handled separately)
                                if ((la.getAttribute('aria-label') || '').toLowerCase().startsWith('download')) return false;
                                return true;
                            })
                            .map(la => la.href);

                        if (!body && !attachments.length) continue;
                        raw.push({ body, isSelf, date: currentDate, time: '', attachments, links });
                    }

                    // Post-process: pair timestamp-only items with the preceding real message
                    // A timestamp-only item has body matching HH:MM or H:MM AM/PM
                    const tsOnly = /^\\d{1,2}:\\d{2}(\\s*(AM|PM))?$/i;
                    // LinkedIn profile card heuristic: body > 150 chars with no sentence structure
                    const isProfileCard = (body) =>
                        body.length > 150 &&
                        (body.includes('1st') || body.includes('2nd') ||
                         body.includes('Premium member') || body.includes('LinkedIn'));

                    const messages = [];
                    for (const item of raw) {
                        const b = item.body;
                        if (tsOnly.test(b)) {
                            // Pair time with most recent real message
                            if (messages.length > 0 && !messages[messages.length - 1].time) {
                                messages[messages.length - 1].time = b;
                            }
                        } else if (!isProfileCard(b)) {
                            messages.push({ sender: '', time: item.time, date: item.date,
                                            body: b, isSelf: item.isSelf,
                                            attachments: item.attachments || [],
                                            links: item.links || [] });
                        }
                    }
                    return messages.length ? messages : null;
                }

                const messages = extractLayoutA() || extractLayoutB() || [];

                const liACount = document.querySelectorAll('li.msg-s-message-list__event').length;
                const liBCount = document.querySelectorAll('li.member-message').length;

                return { tree, messages, debug: { liACount, liBCount } };
            }
        """)

        if not combined or not combined.get("tree"):
            raise ExtractionError("Empty accessibility snapshot from conversation")

        snapshot = combined["tree"]
        dom_raw: list[dict] = combined.get("messages") or []
        dbg = combined.get("debug", {})
        logger.info(
            f"Combined evaluation: {len(dom_raw)} DOM messages, "
            f"layoutA_lis={dbg.get('liACount',0)}, layoutB_lis={dbg.get('liBCount',0)}"
        )

        # Extract connection info - Requirement 5.1
        connection_info = self._connection_extractor.extract_connection_info(
            snapshot, preview.thread_url
        )
        if not connection_info:
            # Fall back to preview data
            connection_info = ConnectionInfo(
                display_name=preview.connection_name,
                linkedin_slug=None,
                profile_url=None,
            )
        # Generate slug if not available
        linkedin_slug = connection_info.linkedin_slug
        if not linkedin_slug:
            # Generate a slug from the display name
            linkedin_slug = self._generate_slug_from_name(connection_info.display_name)

        # Create/update Connection record - Requirement 5.1
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Check if connection already exists to avoid INSERT OR REPLACE issues
        existing_connection = self._connection_repo.get_by_slug(linkedin_slug)
        if existing_connection:
            # Update existing connection using UPDATE WHERE id=? to preserve
            # the primary key and avoid breaking conversation foreign keys.
            existing_connection.display_name = connection_info.display_name
            existing_connection.profile_url = connection_info.profile_url or existing_connection.profile_url
            existing_connection.updated_at = now
            self._connection_repo.update(existing_connection)
            connection = existing_connection
        else:
            # Create new connection
            connection = Connection(
                linkedin_slug=linkedin_slug,
                display_name=connection_info.display_name,
                profile_url=connection_info.profile_url or "",
                first_seen_at=now,
                updated_at=now,
            )
            connection = self._connection_repo.upsert(connection)
        logger.debug(f"Connection: {connection.linkedin_slug} (id={connection.id})")

        # Create/update Conversation record - Requirement 5.2
        # Look up by thread URL first: a previous sync may have stored this conversation
        # under a different connection (e.g. an InMail initially saved with the subject
        # line as display_name).  If the thread URL matches, reuse that record and
        # update its connection_id to the now-correct connection.
        existing_conversation = None
        if preview.thread_url:
            existing_conversation = self._conversation_repo.get_by_thread_url(
                preview.thread_url
            )
            if existing_conversation and existing_conversation.connection_id != connection.id:
                logger.info(
                    f"Re-linking conversation {existing_conversation.id} "
                    f"from connection {existing_conversation.connection_id} "
                    f"to {connection.id}"
                )
                self._conversation_repo.update_connection_id(
                    existing_conversation.id, connection.id  # type: ignore
                )
                existing_conversation.connection_id = connection.id  # type: ignore
        if existing_conversation is None:
            existing_conversation = self._conversation_repo.get_by_connection_id(
                connection.id  # type: ignore
            )
        if existing_conversation:
            # Use existing conversation
            conversation = existing_conversation
            conversation.thread_url = preview.thread_url or conversation.thread_url
            conversation.last_message_at = preview.timestamp or conversation.last_message_at
        else:
            # Create new conversation
            conversation = Conversation(
                connection_id=connection.id,  # type: ignore
                thread_url=preview.thread_url,
                last_message_at=preview.timestamp,
                last_synced_at=None,  # Will be updated after sync
                created_at=now,
            )
            conversation = self._conversation_repo.upsert(conversation)
        logger.debug(f"Conversation: {conversation.id}")

        # Convert pre-fetched DOM raw data to ExtractedMessage list
        # Each entry is (ExtractedMessage, attachment_dicts)
        extracted_messages: list[ExtractedMessage] = []
        extracted_attachments: list[list[dict]] = []
        if dom_raw:
            # First pass: build (body, direction, date_str, time_str, attachments) tuples,
            # filtering out empty messages.
            cooked: list[tuple[str, str, str, str, list[dict]]] = []
            for item in dom_raw:
                body: str = (item.get("body") or "").strip()
                item_attachments: list[dict] = item.get("attachments") or []
                if not body and item_attachments:
                    body = "[attachment: " + ", ".join(
                        a.get("filename") or "file" for a in item_attachments
                    ) + "]"
                if not body:
                    continue
                is_self = item.get("isSelf")
                if is_self is None:
                    sender: str = (item.get("sender") or "").strip()
                    direction = (
                        "inbound"
                        if sender == connection_info.display_name
                        else "outbound"
                    )
                else:
                    direction = "outbound" if is_self else "inbound"
                cooked.append((
                    body,
                    direction,
                    (item.get("date") or "").strip(),
                    (item.get("time") or "").strip(),
                    item_attachments,
                ))

            # Single forward pass (DOM order = oldest → newest).
            # LinkedIn only shows a timestamp on the last message of a consecutive
            # group. Accumulate un-timed messages; when we hit a timed one, assign
            # its time to that message then subtract 1 second per earlier message
            # in the accumulator (preserving order within the group).
            running_date: datetime | None = None
            timestamps: list[datetime | None] = [None] * len(cooked)
            pending: list[int] = []  # indices of un-timed messages awaiting a time anchor

            for idx, (body, direction, date_str, time_str, _) in enumerate(cooked):
                if date_str:
                    date_only = self._parse_dom_timestamp(date_str, "", fallback_date=None)
                    if date_only:
                        running_date = date_only

                if time_str:
                    ts = self._parse_dom_timestamp("", time_str, fallback_date=running_date)
                    if ts:
                        timestamps[idx] = ts
                        for offset, pending_idx in enumerate(reversed(pending), start=1):
                            timestamps[pending_idx] = ts - timedelta(seconds=offset)
                        pending.clear()
                else:
                    pending.append(idx)

            # Messages still pending have no time anchor — place them after the
            # last known timestamp, or at running_date if nothing is known yet.
            last_ts = max((t for t in timestamps if t is not None), default=None)
            for offset, pending_idx in enumerate(pending, start=1):
                if last_ts is not None:
                    timestamps[pending_idx] = last_ts + timedelta(seconds=offset)
                elif running_date is not None:
                    timestamps[pending_idx] = running_date + timedelta(seconds=offset)

            for idx, (body, direction, _, _, item_attachments) in enumerate(cooked):
                extracted_messages.append(
                    ExtractedMessage(
                        content=body,
                        direction=direction,
                        timestamp=timestamps[idx],
                    )
                )
                extracted_attachments.append(item_attachments)
            logger.info(
                f"DOM extraction: {len(extracted_messages)} messages "
                f"(connection='{connection_info.display_name}')"
            )

        if not extracted_messages:
            logger.info("DOM extraction returned no messages, falling back to scroll")
            extracted_messages = await self.scroll_and_extract_messages()
        
        # Report messages extracted - Requirement 3.2
        messages_extracted = len(extracted_messages)
        self._safe_callback(
            progress_callback,
            "messages_extracted",
            {"count": messages_extracted},
        )

        # Store messages with deduplication - Requirement 5.3
        # extracted_attachments is parallel to extracted_messages (may be empty if scroll fallback)
        for i, extracted in enumerate(extracted_messages):
            msg_atts = extracted_attachments[i] if i < len(extracted_attachments) else []
            msg_links: list[str] = (dom_raw[i].get("links") or []) if i < len(dom_raw) else []

            # Resolve timestamp: use now() as fallback so Message validates
            msg_timestamp = extracted.timestamp or now

            # Determine sender_id
            sender_id: int | None = None
            if extracted.direction == "inbound":
                sender_id = connection.id

            # Generate dedup key to check for existing message
            dedup_key = self._message_repo.generate_dedup_key(
                conversation.id,  # type: ignore
                msg_timestamp,
                extracted.content,
                extracted.direction,
            )

            # Check if message already exists
            existing_messages = self._message_repo.get_by_conversation(conversation.id)  # type: ignore
            is_duplicate = any(msg.dedup_key == dedup_key for msg in existing_messages)

            if is_duplicate:
                messages_skipped += 1
            else:
                message = Message(
                    conversation_id=conversation.id,  # type: ignore
                    linkedin_msg_id=None,
                    sender_id=sender_id,
                    content=extracted.content,
                    timestamp=msg_timestamp,
                    direction=extracted.direction,
                    synced_at=now,
                    dedup_key=dedup_key,
                )
                stored_message = self._message_repo.store(message)
                messages_stored += 1

                # Download and store attachments for this message
                for att in msg_atts:
                    await self._download_and_store_attachment(
                        stored_message.id,  # type: ignore
                        att,
                    )

                # Scrape outbound links found in the message
                await self._scrape_and_store_links(
                    stored_message.id,  # type: ignore
                    extracted.content,
                    msg_atts and [a.get("href", "") for a in msg_atts] or [],
                    msg_links,
                )

        # Report messages stored - Requirement 3.3
        self._safe_callback(
            progress_callback,
            "messages_stored",
            {"new": messages_stored, "skipped": messages_skipped},
        )

        # Update last_message_at from actual message timestamps (only if new messages were stored)
        if messages_stored > 0 and extracted_messages:
            ts_values = [msg.timestamp for msg in extracted_messages if msg.timestamp]
            latest_ts = max(ts_values) if ts_values else None
            self._conversation_repo.update_last_message_at(
                conversation.id,  # type: ignore
                latest_ts,
            )

        # Update last_synced_at timestamp - Requirement 5.4
        self._conversation_repo.update_sync_timestamp(
            conversation.id,  # type: ignore
            now,
        )

        logger.info(
            f"Synced conversation '{preview.connection_name}': "
            f"{messages_stored} new, {messages_skipped} skipped"
        )

        return messages_stored, messages_skipped, messages_extracted

    @staticmethod
    def _dereference_url(url: str) -> str:
        """Resolve LinkedIn safety/redirect wrapper to the actual destination URL.

        Handles:
        - linkedin.com/safety/go?url=<encoded>
        - linkedin.com/redir/redirect?url=<encoded>

        Args:
            url: Raw URL, possibly a LinkedIn interstitial

        Returns:
            The real destination URL, or the original if no wrapping detected
        """
        from urllib.parse import parse_qs, urlparse, unquote

        parsed = urlparse(url)
        if "linkedin.com" in parsed.netloc and parsed.path in ("/safety/go", "/redir/redirect"):
            params = parse_qs(parsed.query)
            if "url" in params:
                return unquote(params["url"][0])
        return url

    async def _scrape_and_store_links(
        self,
        message_id: int,
        content: str,
        _unused_att_hrefs: list[str],
        dom_links: list[str],
    ) -> None:
        """Scrape outbound URLs extracted from the message DOM and store as text attachments.

        Uses hrefs from the DOM (more authoritative than text regex) and
        dereferences LinkedIn safety interstitial URLs before scraping.
        Falls back to regex on content if no DOM links were provided.
        Runs trafilatura in a thread executor (it is synchronous).

        Args:
            message_id: ID of the message to attach scraped content to
            content: Raw message text (used as fallback URL source)
            _unused_att_hrefs: Unused (kept for call-site compatibility)
            dom_links: Hrefs extracted from <a> tags in the message DOM
        """
        import asyncio
        from urllib.parse import urlparse

        import trafilatura

        from dm_bot.storage import Attachment, AttachmentRepository, DB_PATH

        # Prefer DOM hrefs; fall back to regex on content text
        if dom_links:
            raw_urls = dom_links
        else:
            raw_urls = self._URL_RE.findall(content)

        if not raw_urls:
            return

        # Dereference LinkedIn interstitials and deduplicate
        seen: set[str] = set()
        urls: list[str] = []
        for raw in raw_urls:
            resolved = self._dereference_url(raw)
            if resolved not in seen:
                seen.add(resolved)
                urls.append(resolved)

        # Skip any remaining LinkedIn URLs (e.g. safety/go that didn't resolve)
        # Also skip URLs whose hostname starts with an uppercase letter (e.g. Next.js, Node.js)
        urls = [
            u for u in urls
            if "linkedin.com" not in urlparse(u).netloc
            and urlparse(u).netloc[:1].islower()
        ]
        if not urls:
            return

        attachments_dir = DB_PATH.parent / "attachments"
        attachments_dir.mkdir(exist_ok=True)

        loop = asyncio.get_event_loop()

        for i, url in enumerate(urls):
            domain = urlparse(url).netloc.lstrip("www.")
            try:
                downloaded = await loop.run_in_executor(
                    None, trafilatura.fetch_url, url
                )
                if not downloaded:
                    logger.debug(f"trafilatura: no content fetched from {url}")
                    continue

                text = await loop.run_in_executor(
                    None,
                    lambda d=downloaded: trafilatura.extract(
                        d, include_comments=False, include_tables=True
                    ),
                )
                if not text:
                    logger.debug(f"trafilatura: no text extracted from {url}")
                    continue

                safe_domain = re.sub(r"[^\w\-.]", "_", domain)[:50]
                original_filename = f"web_{i}_{safe_domain}.txt"
                filename = AttachmentRepository.make_filename(message_id, original_filename)
                file_path = attachments_dir / filename
                file_path.write_text(text, encoding="utf-8")
                file_bytes = len(text.encode("utf-8"))

                self._attachment_repo.store(
                    Attachment(
                        message_id=message_id,
                        attachment_path=str(file_path),
                        original_filename=original_filename,
                        content_type="text/plain",
                        file_size=file_bytes,
                    )
                )
                logger.info(
                    f"Scraped and saved: {file_path} ({file_bytes:,} bytes) from {url}"
                )

            except Exception as exc:
                logger.warning(f"Failed to scrape {url}: {exc}")

    # Regex fallback: find URLs in plain text.
    # Hostname must start with a lowercase letter or digit (real hostnames are lowercase;
    # bare tech names like "Next.js" and "Node.js" start with uppercase and are rejected).
    _URL_RE = re.compile(r"https?://[a-z0-9][^\s<>\"')\]]*")

    async def _download_and_store_attachment(
        self, message_id: int, att: dict
    ) -> None:
        """Download an attachment via the browser and persist it to disk and DB.

        Uses page.evaluate fetch() so the browser's cookie jar is used for auth.
        Saves to .persistence/attachments/{message_id}_{original_filename}.

        Args:
            message_id: ID of the message this attachment belongs to
            att: Dict with keys ``href``, ``filename``, ``label``
        """
        import base64

        from dm_bot.storage import Attachment, AttachmentRepository, DB_PATH

        href: str = (att.get("href") or "").strip()
        original_filename: str = (att.get("filename") or att.get("label") or "attachment").strip()
        # Sanitize filename: remove path separators and null bytes
        original_filename = original_filename.replace("/", "_").replace("\x00", "")

        if not href:
            logger.warning("Attachment has no href, skipping download")
            return

        try:
            b64: str | None = await self._page.evaluate(
                """
                async (url) => {
                    const r = await fetch(url);
                    if (!r.ok) return null;
                    const buf = await r.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let bin = '';
                    for (const b of bytes) bin += String.fromCharCode(b);
                    return btoa(bin);
                }
                """,
                href,
            )
        except Exception as exc:
            logger.warning(f"Failed to fetch attachment '{original_filename}': {exc}")
            return

        if not b64:
            logger.warning(f"Attachment download returned null for '{original_filename}'")
            return

        file_bytes = base64.b64decode(b64)

        attachments_dir = DB_PATH.parent / "attachments"
        attachments_dir.mkdir(exist_ok=True)

        filename = AttachmentRepository.make_filename(message_id, original_filename)
        file_path = attachments_dir / filename
        file_path.write_bytes(file_bytes)

        self._attachment_repo.store(
            Attachment(
                message_id=message_id,
                attachment_path=str(file_path),
                original_filename=original_filename,
                file_size=len(file_bytes),
            )
        )
        logger.info(f"Saved attachment: {file_path} ({len(file_bytes):,} bytes)")

    async def send_message(
        self, thread_url: str, message: str, attachment_path: str | None = None
    ) -> bool:
        """Navigate to thread, type and send message. Returns True on success.

        Args:
            thread_url: URL of the conversation thread.
            message: Text content to send.
            attachment_path: Optional path to a file to attach before sending.
        """
        await self._page.goto(thread_url)
        await self._rate_limiter.delay_after_page_load()

        # Handle login redirect (same pattern as sync_single_conversation)
        if "/login" in self._page.url or "/uas/login" in self._page.url:
            logger.warning("Thread URL redirected to login page; filling credentials")
            from dm_bot.config import LI_USER, LI_PASS
            try:
                email_field = await self._page.query_selector(
                    'input[type="email"], input[name="session_key"], '
                    'input[autocomplete="username"]'
                )
                if email_field and await email_field.is_visible():
                    await email_field.fill(LI_USER or "")
                    await asyncio.sleep(0.5)
                try:
                    cont = await self._page.wait_for_selector(
                        'button[type="submit"]:not([data-id="sign-in-form__submit-btn"])',
                        timeout=1500,
                    )
                    if cont:
                        await cont.click()
                        await asyncio.sleep(2)
                except Exception:
                    pass
                pwd_field = await self._page.wait_for_selector(
                    'input[type="password"]', timeout=5000
                )
                await pwd_field.fill(LI_PASS or "")
                await asyncio.sleep(0.5)
                sign_in = await self._page.wait_for_selector(
                    'button[type="submit"], button[data-id="sign-in-form__submit-btn"]',
                    timeout=3000,
                )
                await sign_in.click()
                await asyncio.sleep(3)
                if "/login" in self._page.url:
                    raise ExtractionError("Re-login failed; please log in manually and retry")
                await self._page.goto(thread_url)
                await self._rate_limiter.delay_after_page_load()
            except ExtractionError:
                raise
            except Exception as e:
                raise ExtractionError(f"Re-login error: {e}") from e

        # Wait for conversation to load
        await self._page.wait_for_selector(
            "li.msg-s-message-list__event, li.member-message", timeout=20000
        )

        # Focus the message composer (mobile layout uses textarea)
        composer = await self._page.wait_for_selector(
            "textarea, div[contenteditable='true']", timeout=10000
        )
        await composer.click()
        await asyncio.sleep(0.3)

        # Paste the full message at once
        await composer.fill(message)
        await asyncio.sleep(0.3)

        # Attach file if provided
        if attachment_path is not None:
            # The file input is a sibling of the "Attach a file" button inside the
            # composer footer. It is hidden so we set files directly without clicking.
            file_input = await self._page.query_selector(
                "div[aria-label*='Attach a file'] input[type='file'], "
                "footer input[type='file']:not([accept='image/*'])"
            )
            if file_input is None:
                # Broader fallback: any file input in the composer area
                file_input = await self._page.query_selector(
                    "form input[type='file'], footer input[type='file']"
                )
            if file_input is None:
                raise ExtractionError("Could not find file input for attachment")
            await file_input.set_input_files(attachment_path)
            logger.info(f"Attachment set: {attachment_path}")
            # Wait for upload indicator to appear/disappear
            await asyncio.sleep(2.0)

        # Click Send button — try CSS selectors covering desktop + mwlite layouts
        send_btn = await self._page.wait_for_selector(
            "button.message-send, "
            "button[aria-label='Send Message'], "
            "button.msg-form__send-btn, "
            "button[data-control-name='send'], "
            "button[aria-label*='Send']",
            timeout=5000,
        )
        await send_btn.click()
        await asyncio.sleep(1.5)

        logger.info(f"Message sent to thread: {thread_url}")
        return True

    def _generate_slug_from_name(self, name: str) -> str:
        """Generate a URL-safe slug from a display name.

        Args:
            name: Display name to convert

        Returns:
            URL-safe slug string
        """
        import re
        import hashlib

        # Convert to lowercase and replace spaces with hyphens
        slug = name.lower().strip()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-")

        # If slug is empty or too short, use a hash
        if len(slug) < 3:
            hash_suffix = hashlib.md5(name.encode()).hexdigest()[:8]
            slug = f"user-{hash_suffix}"

        return slug

    async def _scroll_conversation_to_top(self, max_scrolls: int = 30) -> None:
        """Scroll the conversation up until no new messages load (top reached).

        LinkedIn lazy-loads older messages as you scroll up. We keep scrolling
        until the li count stabilises so that all date separators are present
        in the DOM before we extract messages and timestamps.
        """
        _SCROLL_JS = """
            () => {
                const count = document.querySelectorAll(
                    'li.msg-s-message-list__event, li.member-message'
                ).length;

                // Scroll the message container to the top
                const bySelector = document.querySelector(
                    '[role="log"], .msg-s-message-list'
                );
                if (bySelector && bySelector.scrollHeight > bySelector.clientHeight) {
                    bySelector.scrollTop = 0;
                } else {
                    const main = document.querySelector('main');
                    const candidates = main
                        ? Array.from(main.querySelectorAll('div'))
                        : Array.from(document.querySelectorAll('div'));
                    let best = null, bestH = 0;
                    for (const el of candidates) {
                        if (el.scrollHeight > el.clientHeight && el.scrollHeight > bestH) {
                            best = el; bestH = el.scrollHeight;
                        }
                    }
                    if (best) best.scrollTop = 0;
                    else window.scrollTo(0, 0);
                }
                return count;
            }
        """
        prev_count = -1
        for attempt in range(max_scrolls):
            try:
                count: int = await self._page.evaluate(_SCROLL_JS)
            except Exception as e:
                logger.debug(f"Scroll-to-top attempt {attempt + 1} failed: {e}")
                break
            logger.debug(f"Scroll-to-top {attempt + 1}: {count} lis (prev {prev_count})")
            if count == prev_count:
                logger.info(f"Reached top of conversation after {attempt} scrolls ({count} lis)")
                break
            prev_count = count
            await asyncio.sleep(1.5)
        else:
            logger.info(f"Scroll-to-top: hit max_scrolls={max_scrolls} ({prev_count} lis)")

    def _parse_dom_timestamp(
        self, date_str: str, time_str: str, fallback_date: datetime | None = None
    ) -> datetime | None:
        """Parse a date + time pair from the DOM message structure.

        Args:
            date_str: Date string like "Jul 4, 2024", ISO "2024-07-04T15:59:00",
                      or "" if not set yet.
            time_str: Time string like "3:59 PM", "16:01", or "" if embedded in date_str.
            fallback_date: Date to use when only a time is available (no in-thread date
                           separator). Typically ``preview.timestamp`` from the inbox list,
                           which shows the date of the most recent message.

        Returns:
            Parsed datetime, or None if parsing fails.
        """
        import re as _re
        now = datetime.now()

        # Try ISO datetime first (from <time datetime="...">)
        # Handles "2024-07-04T15:59:00", "2024-07-04T15:59:00.000Z"
        for candidate in (time_str.strip(), date_str.strip()):
            iso_dt = _re.match(
                r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})",
                candidate
            )
            if iso_dt:
                try:
                    # ISO timestamps from LinkedIn's <time datetime> are local time
                    return _local_to_utc(datetime(
                        int(iso_dt.group(1)), int(iso_dt.group(2)),
                        int(iso_dt.group(3)), int(iso_dt.group(4)),
                        int(iso_dt.group(5)),
                    ))
                except ValueError:
                    pass

        # Date-only ISO: "2024-07-04"
        for candidate in (date_str.strip(), time_str.strip()):
            iso_d = _re.match(r"^(\d{4})-(\d{2})-(\d{2})$", candidate)
            if iso_d:
                try:
                    return _local_to_utc(datetime(
                        int(iso_d.group(1)), int(iso_d.group(2)),
                        int(iso_d.group(3)),
                    ))
                except ValueError:
                    pass

        # Parse the time part (Layout A / standalone time strings)
        hour = minute = None
        m = _re.match(r"^(\d{1,2}):(\d{2})\s*(AM|PM)$", time_str.strip(), _re.IGNORECASE)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            ampm = m.group(3).upper()
            if ampm == "PM" and hour != 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0
        else:
            m24 = _re.match(r"^(\d{1,2}):(\d{2})$", time_str.strip())
            if m24:
                hour, minute = int(m24.group(1)), int(m24.group(2))

        # Parse the date part — various LinkedIn separator formats
        year = month = day = None
        if date_str:
            ds = date_str.strip()
            _MONTH_MAP = {
                "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
                "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
                "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
            }
            # "Jul 4, 2024" or "Mar 20, 2025"
            m_full = _re.match(r"^([A-Z][a-z]{2})\s+(\d{1,2}),?\s*(\d{4})$", ds)
            if m_full:
                month = _MONTH_MAP.get(m_full.group(1))
                day = int(m_full.group(2))
                year = int(m_full.group(3))
            else:
                # "Mar 20" — current year implied
                m_short = _re.match(r"^([A-Z][a-z]{2})\s+(\d{1,2})$", ds)
                if m_short:
                    month = _MONTH_MAP.get(m_short.group(1))
                    day = int(m_short.group(2))
                    year = now.year
                else:
                    # Day-of-week within last 6 days — resolve to exact date
                    _DOW = {
                        "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
                        "Friday": 4, "Saturday": 5, "Sunday": 6,
                    }
                    if ds in _DOW:
                        target_dow = _DOW[ds]
                        delta = (now.weekday() - target_dow) % 7
                        if delta == 0:
                            delta = 7  # "Monday" means last Monday, not today
                        ref = now - timedelta(days=delta)
                        year, month, day = ref.year, ref.month, ref.day
                    elif ds.lower() == "today":
                        year, month, day = now.year, now.month, now.day
                    elif ds.lower() == "yesterday":
                        ref = now - timedelta(days=1)
                        year, month, day = ref.year, ref.month, ref.day

        if hour is None:
            # Time unknown but date known → return a naive local-time midnight.
            # Do NOT apply UTC conversion here: callers use the date-only result
            # as a `fallback_date` carrier for subsequent time parsing on the same
            # message, and BST→UTC of midnight shifts the date back a day (e.g.
            # `May 13 00:00 BST → May 12 23:00 UTC`), causing every message
            # timestamp built from this carrier to be off by 1 day.
            if year and month and day:
                return datetime(year, month, day)
            return None

        if year and month and day:
            return _local_to_utc(datetime(year, month, day, hour, minute or 0))

        # No date from in-thread separator: use fallback_date if available, else today.
        # Adjust back one day if the result would be in the future.
        base = fallback_date if fallback_date is not None else now
        result = datetime(base.year, base.month, base.day, hour, minute or 0)
        if result > now:
            result -= timedelta(days=1)
        return _local_to_utc(result)

    async def _extract_messages_from_dom(
        self, connection_name: str
    ) -> list[ExtractedMessage]:
        """Extract messages directly from the DOM using CSS selectors.

        This is more reliable than the accessibility-tree approach because:
        - Each li.msg-s-message-list__event = one message (correct 1:1 mapping)
        - Sender name is explicit in span.msg-s-message-group__name
        - Date separators are tracked per-message group

        Args:
            connection_name: Display name of the other person in the conversation.
                Messages from this name are RECEIVED; all others are SENT.

        Returns:
            List of ExtractedMessage objects.
        """
        try:
            raw = await self._page.evaluate("""
                () => {
                    const lis = document.querySelectorAll(
                        'li.msg-s-message-list__event'
                    );
                    let currentDate = '';
                    const results = [];

                    for (const li of lis) {
                        // Track the current date separator
                        const dateEl = li.querySelector(
                            'time.msg-s-message-list__time-heading'
                        );
                        if (dateEl) {
                            currentDate = (dateEl.textContent || '').trim();
                        }

                        const senderEl = li.querySelector(
                            '.msg-s-message-group__name'
                        );
                        const timeEl = li.querySelector(
                            'time.msg-s-message-group__timestamp'
                        );
                        const bodyEl = li.querySelector(
                            'p.msg-s-event-listitem__body'
                        );
                        const subjectEl = li.querySelector(
                            'h3.msg-s-event-listitem__subject'
                        );

                        const sender = (senderEl?.textContent || '').trim();
                        const time   = (timeEl?.textContent   || '').trim();
                        let   body   = (bodyEl?.textContent   || '').trim();
                        const subject = (subjectEl?.textContent || '').trim();

                        if (!body && !subject) continue;
                        if (subject) body = subject + '\\n' + body;

                        results.push({
                            sender,
                            time,
                            date: currentDate,
                            body,
                        });
                    }
                    return results;
                }
            """)
        except Exception as e:
            logger.warning(f"DOM message extraction failed: {e}")
            return []

        if not raw:
            return []

        messages: list[ExtractedMessage] = []
        for item in raw:
            body: str = (item.get("body") or "").strip()
            sender: str = (item.get("sender") or "").strip()
            time_str: str = (item.get("time") or "").strip()
            date_str: str = (item.get("date") or "").strip()

            if not body:
                continue

            direction: str = (
                "inbound" if sender == connection_name else "outbound"
            )
            timestamp = self._parse_dom_timestamp(date_str, time_str)

            messages.append(
                ExtractedMessage(
                    content=body,
                    direction=direction,
                    timestamp=timestamp,
                )
            )

        logger.info(f"DOM extraction: {len(messages)} messages found")
        return messages

    async def scroll_and_extract_messages(
        self,
        max_scrolls: int = 10,
    ) -> list[ExtractedMessage]:
        """Scroll conversation to load all messages, then extract.

        Scrolls the conversation container to load older messages,
        waiting for new content between scrolls. Respects rate limiting.

        Args:
            max_scrolls: Maximum number of scroll attempts (default 10)

        Returns:
            List of ExtractedMessage objects from the conversation

        Requirements:
            - 4.1: Scroll to load additional messages
            - 4.2: Wait for new content between scrolls
            - 4.3: Stop when no new messages load
            - 4.4: Respect rate limiting delays
        """
        all_messages: list[ExtractedMessage] = []
        previous_count = 0

        for scroll_num in range(max_scrolls):
            # Get current snapshot and extract messages
            snapshot = await self._get_accessibility_snapshot()
            if not snapshot:
                break

            current_messages = self._message_extractor.extract_messages(snapshot)
            current_count = len(current_messages)

            logger.debug(
                f"Scroll {scroll_num + 1}: found {current_count} messages "
                f"(previous: {previous_count})"
            )

            # Check if we got new messages - Requirement 4.3
            if current_count <= previous_count:
                logger.debug("No new messages after scroll, stopping")
                break

            all_messages = current_messages
            previous_count = current_count

            # Try to scroll up to load older messages - Requirement 4.1
            try:
                # Find message container and scroll to top to trigger lazy-load of older messages.
                # On mobile LinkedIn the container is a plain scrollable div (no role="log").
                # Strategy: find the tallest scrollable div inside main, or fall back to window.
                scrolled = await self._page.evaluate("""
                    () => {
                        // Try known selectors first
                        const bySelector = document.querySelector(
                            '[role="log"], [role="list"], .msg-s-message-list'
                        );
                        if (bySelector && bySelector.scrollHeight > bySelector.clientHeight) {
                            bySelector.scrollTop = 0;
                            return 'selector';
                        }
                        // Walk divs inside <main> to find the scrollable message container
                        const main = document.querySelector('main');
                        const candidates = main
                            ? Array.from(main.querySelectorAll('div'))
                            : Array.from(document.querySelectorAll('div'));
                        // Pick the div with the largest scrollHeight that is actually scrollable
                        let best = null;
                        let bestHeight = 0;
                        for (const el of candidates) {
                            if (el.scrollHeight > el.clientHeight && el.scrollHeight > bestHeight) {
                                best = el;
                                bestHeight = el.scrollHeight;
                            }
                        }
                        if (best) {
                            best.scrollTop = 0;
                            return 'div:' + bestHeight;
                        }
                        window.scrollTo(0, 0);
                        return 'window';
                    }
                """)
                logger.debug(f"Scroll {scroll_num + 1}: scrolled via {scrolled}")
            except Exception as e:
                logger.debug(f"Scroll failed: {e}")
                break

            # Wait longer for LinkedIn to lazy-load older messages - Requirement 4.2
            await asyncio.sleep(2)
            await self._rate_limiter.delay_between_actions()

        logger.info(f"Extracted {len(all_messages)} messages after scrolling")
        return all_messages
