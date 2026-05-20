"""Tests for progress callback functionality in SyncEngine.

This module tests that the progress callback is invoked at the correct
points during the sync process with the correct event types and data.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock
from dm_bot.extraction import (
    SyncEngine,
    ConversationPreview,
)
from tests.test_extraction import (
    create_temp_db,
    create_mock_page,
    create_mock_rate_limiter,
    create_mock_notifier,
)


@pytest.mark.asyncio
async def test_progress_callback_invoked_for_conversation_start() -> None:
    """Test that progress callback is invoked when conversation starts.
    
    Verifies that the callback receives:
    - event_type: "conversation_start"
    - data: {"index": int, "total": int, "name": str}
    """
    # Setup
    temp_db = create_temp_db()
    mock_page = create_mock_page()
    mock_rate_limiter = create_mock_rate_limiter()
    mock_notifier = create_mock_notifier()
    
    # Create a mock callback
    callback = Mock()
    
    # Create mock inbox snapshot with one conversation
    inbox_snapshot = {
        "role": "WebArea",
        "name": "LinkedIn",
        "children": [
            {
                "role": "main",
                "name": "Main content",
                "children": [
                    {
                        "role": "list",
                        "name": "Conversations",
                        "children": [
                            {
                                "role": "listitem",
                                "name": "John Doe",
                                "children": [
                                    {
                                        "role": "link",
                                        "name": "John Doe",
                                        "url": "https://www.linkedin.com/messaging/thread/john-doe/",
                                    },
                                    {"role": "text", "name": "Last message snippet"},
                                    {"role": "text", "name": "10:30 AM"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    
    # Create mock conversation snapshot
    conversation_snapshot = {
        "role": "WebArea",
        "name": "LinkedIn",
        "children": [
            {
                "role": "main",
                "name": "Main content",
                "children": [
                    {
                        "role": "heading",
                        "name": "John Doe",
                        "children": [
                            {
                                "role": "link",
                                "name": "John Doe",
                                "url": "https://www.linkedin.com/in/john-doe/",
                            }
                        ],
                    },
                    {
                        "role": "list",
                        "name": "Messages",
                        "children": [
                            {
                                "role": "listitem",
                                "name": "Hello",
                                "description": "received",
                                "children": [
                                    {"role": "text", "name": "Hello"},
                                    {"role": "text", "name": "10:30 AM"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    
    # Configure mock page evaluate with appropriate side effects.
    # Inbox-collection phase (anchor=None, limit=None → scroll until DOM stable):
    #   iter 1: snapshot + enrich → 1 preview, prev_dom=-1, scroll → continue
    #   iter 2: snapshot + enrich → 1 preview, dom_count==prev_dom=1 → break
    # Conversation-sync phase:
    #   initial snapshot, scroll iter 1 (N=1 > 0, continue), scroll JS,
    #   scroll iter 2 (N=1, stable, break).
    mock_page.evaluate = AsyncMock(
        side_effect=[
            inbox_snapshot,           # inbox iter 1 snapshot
            [],                       # inbox iter 1 enrich URLs
            None,                     # inbox scroll JS
            inbox_snapshot,           # inbox iter 2 snapshot
            [],                       # inbox iter 2 enrich URLs (stable → break)
            conversation_snapshot,    # sync_single_conversation initial snapshot
            conversation_snapshot,    # convo scroll-to-top iter 1
            None,                     # convo scroll-to-top JS
            conversation_snapshot,    # convo scroll-to-top iter 2 (stable, break)
        ]
    )

    # Create SyncEngine
    engine = SyncEngine(
        page=mock_page,
        db=temp_db,
        rate_limiter=mock_rate_limiter,
        notifier=mock_notifier,
    )

    # Execute sync with callback
    await engine.sync_conversations(progress_callback=callback)
    
    # Verify callback was invoked for conversation_start
    assert callback.call_count >= 1
    
    # Find the conversation_start call
    conversation_start_calls = [
        call for call in callback.call_args_list
        if call[0][0] == "conversation_start"
    ]
    
    assert len(conversation_start_calls) == 1
    event_type, data = conversation_start_calls[0][0]
    
    assert event_type == "conversation_start"
    assert "index" in data
    assert "total" in data
    assert "name" in data
    assert data["index"] == 1
    assert data["total"] == 1
    assert data["name"] == "John Doe"


@pytest.mark.asyncio
async def test_progress_callback_invoked_for_messages_extracted() -> None:
    """Test that progress callback is invoked when messages are extracted.
    
    Verifies that the callback receives:
    - event_type: "messages_extracted"
    - data: {"count": int}
    """
    # Setup
    temp_db = create_temp_db()
    mock_page = create_mock_page()
    mock_rate_limiter = create_mock_rate_limiter()
    mock_notifier = create_mock_notifier()
    
    callback = Mock()
    
    # Create conversation snapshot with 3 messages
    conversation_snapshot = {
        "role": "WebArea",
        "name": "LinkedIn",
        "children": [
            {
                "role": "main",
                "name": "Main content",
                "children": [
                    {
                        "role": "heading",
                        "name": "Jane Smith",
                        "children": [
                            {
                                "role": "link",
                                "name": "Jane Smith",
                                "url": "https://www.linkedin.com/in/jane-smith/",
                            }
                        ],
                    },
                    {
                        "role": "list",
                        "name": "Messages",
                        "children": [
                            {
                                "role": "listitem",
                                "name": "Message 1",
                                "description": "received",
                                "children": [
                                    {"role": "text", "name": "Message 1"},
                                    {"role": "text", "name": "10:00 AM"},
                                ],
                            },
                            {
                                "role": "listitem",
                                "name": "Message 2",
                                "description": "sent",
                                "children": [
                                    {"role": "text", "name": "Message 2"},
                                    {"role": "text", "name": "10:05 AM"},
                                ],
                            },
                            {
                                "role": "listitem",
                                "name": "Message 3",
                                "description": "received",
                                "children": [
                                    {"role": "text", "name": "Message 3"},
                                    {"role": "text", "name": "10:10 AM"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    
    mock_page.evaluate = AsyncMock(return_value=conversation_snapshot)

    engine = SyncEngine(
        page=mock_page,
        db=temp_db,
        rate_limiter=mock_rate_limiter,
        notifier=mock_notifier,
    )

    preview = ConversationPreview(
        connection_name="Jane Smith",
        last_message_snippet="Message 3",
        timestamp=datetime.now(),
        thread_url="https://www.linkedin.com/messaging/thread/jane-smith/",
    )

    # Execute sync_single_conversation with callback
    await engine.sync_single_conversation(preview, progress_callback=callback)

    # Verify callback was invoked for messages_extracted
    messages_extracted_calls = [
        call for call in callback.call_args_list
        if call[0][0] == "messages_extracted"
    ]
    
    assert len(messages_extracted_calls) == 1
    event_type, data = messages_extracted_calls[0][0]
    
    assert event_type == "messages_extracted"
    assert "count" in data
    assert data["count"] == 3


@pytest.mark.asyncio
async def test_progress_callback_invoked_for_messages_stored() -> None:
    """Test that progress callback is invoked when messages are stored.
    
    Verifies that the callback receives:
    - event_type: "messages_stored"
    - data: {"new": int, "skipped": int}
    """
    # Setup
    temp_db = create_temp_db()
    mock_page = create_mock_page()
    mock_rate_limiter = create_mock_rate_limiter()
    mock_notifier = create_mock_notifier()
    
    callback = Mock()
    
    # Create conversation snapshot with 2 messages
    conversation_snapshot = {
        "role": "WebArea",
        "name": "LinkedIn",
        "children": [
            {
                "role": "main",
                "name": "Main content",
                "children": [
                    {
                        "role": "heading",
                        "name": "Bob Johnson",
                        "children": [
                            {
                                "role": "link",
                                "name": "Bob Johnson",
                                "url": "https://www.linkedin.com/in/bob-johnson/",
                            }
                        ],
                    },
                    {
                        "role": "list",
                        "name": "Messages",
                        "children": [
                            {
                                "role": "listitem",
                                "name": "Hello Bob",
                                "description": "sent",
                                "children": [
                                    {"role": "text", "name": "Hello Bob"},
                                    {"role": "text", "name": "9:00 AM"},
                                ],
                            },
                            {
                                "role": "listitem",
                                "name": "Hi there",
                                "description": "received",
                                "children": [
                                    {"role": "text", "name": "Hi there"},
                                    {"role": "text", "name": "9:05 AM"},
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    
    mock_page.evaluate = AsyncMock(return_value=conversation_snapshot)

    engine = SyncEngine(
        page=mock_page,
        db=temp_db,
        rate_limiter=mock_rate_limiter,
        notifier=mock_notifier,
    )

    preview = ConversationPreview(
        connection_name="Bob Johnson",
        last_message_snippet="Hi there",
        timestamp=datetime.now(),
        thread_url="https://www.linkedin.com/messaging/thread/bob-johnson/",
    )

    # Execute sync_single_conversation with callback
    await engine.sync_single_conversation(preview, progress_callback=callback)

    # Verify callback was invoked for messages_stored
    messages_stored_calls = [
        call for call in callback.call_args_list
        if call[0][0] == "messages_stored"
    ]
    
    assert len(messages_stored_calls) == 1
    event_type, data = messages_stored_calls[0][0]
    
    assert event_type == "messages_stored"
    assert "new" in data
    assert "skipped" in data
    assert data["new"] == 2
    assert data["skipped"] == 0


@pytest.mark.asyncio
async def test_progress_callback_failure_does_not_break_sync() -> None:
    """Test that callback exceptions don't break the sync process.
    
    Verifies that even if the callback raises an exception,
    the sync continues and completes successfully.
    """
    # Setup
    temp_db = create_temp_db()
    mock_page = create_mock_page()
    mock_rate_limiter = create_mock_rate_limiter()
    mock_notifier = create_mock_notifier()
    
    # Create a callback that always raises an exception
    def failing_callback(event_type: str, data: dict) -> None:
        raise RuntimeError("Callback failed!")
    
    # Create mock inbox snapshot
    inbox_snapshot = {
        "role": "WebArea",
        "name": "LinkedIn",
        "children": [
            {
                "role": "main",
                "name": "Main content",
                "children": [
                    {
                        "role": "list",
                        "name": "Conversations",
                        "children": [
                            {
                                "role": "listitem",
                                "name": "Test User",
                                "children": [
                                    {
                                        "role": "link",
                                        "name": "Test User",
                                        "url": "https://www.linkedin.com/messaging/thread/test-user/",
                                    },
                                    {"role": "text", "name": "Test message"},
                                    {"role": "text", "name": "11:00 AM"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    
    conversation_snapshot = {
        "role": "WebArea",
        "name": "LinkedIn",
        "children": [
            {
                "role": "main",
                "name": "Main content",
                "children": [
                    {
                        "role": "heading",
                        "name": "Test User",
                        "children": [
                            {
                                "role": "link",
                                "name": "Test User",
                                "url": "https://www.linkedin.com/in/test-user/",
                            }
                        ],
                    },
                    {
                        "role": "list",
                        "name": "Messages",
                        "children": [
                            {
                                "role": "listitem",
                                "name": "Test message",
                                "description": "received",
                                "children": [
                                    {"role": "text", "name": "Test message"},
                                    {"role": "text", "name": "11:00 AM"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    
    mock_page.evaluate = AsyncMock(
        side_effect=[
            inbox_snapshot,           # inbox iter 1 snapshot
            [],                       # inbox iter 1 enrich URLs
            None,                     # inbox scroll JS
            inbox_snapshot,           # inbox iter 2 snapshot
            [],                       # inbox iter 2 enrich URLs (stable → break)
            conversation_snapshot,    # sync_single_conversation initial snapshot
            conversation_snapshot,    # convo scroll-to-top iter 1
            None,                     # convo scroll-to-top JS
            conversation_snapshot,    # convo scroll-to-top iter 2 (stable, break)
        ]
    )

    engine = SyncEngine(
        page=mock_page,
        db=temp_db,
        rate_limiter=mock_rate_limiter,
        notifier=mock_notifier,
    )

    # Execute sync with failing callback - should not raise exception
    result = await engine.sync_conversations(progress_callback=failing_callback)
    
    # Verify sync completed successfully despite callback failures
    assert result.conversations_processed == 1
    assert result.messages_stored == 1
    assert result.messages_skipped == 0
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_sync_without_callback_works() -> None:
    """Test that sync works normally when no callback is provided.
    
    Verifies backward compatibility - sync should work without a callback.
    """
    # Setup
    temp_db = create_temp_db()
    mock_page = create_mock_page()
    mock_rate_limiter = create_mock_rate_limiter()
    mock_notifier = create_mock_notifier()
    
    inbox_snapshot = {
        "role": "WebArea",
        "name": "LinkedIn",
        "children": [
            {
                "role": "main",
                "name": "Main content",
                "children": [
                    {
                        "role": "list",
                        "name": "Conversations",
                        "children": [
                            {
                                "role": "listitem",
                                "name": "Alice Cooper",
                                "children": [
                                    {
                                        "role": "link",
                                        "name": "Alice Cooper",
                                        "url": "https://www.linkedin.com/messaging/thread/alice-cooper/",
                                    },
                                    {"role": "text", "name": "Hey there"},
                                    {"role": "text", "name": "2:00 PM"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    
    conversation_snapshot = {
        "role": "WebArea",
        "name": "LinkedIn",
        "children": [
            {
                "role": "main",
                "name": "Main content",
                "children": [
                    {
                        "role": "heading",
                        "name": "Alice Cooper",
                        "children": [
                            {
                                "role": "link",
                                "name": "Alice Cooper",
                                "url": "https://www.linkedin.com/in/alice-cooper/",
                            }
                        ],
                    },
                    {
                        "role": "list",
                        "name": "Messages",
                        "children": [
                            {
                                "role": "listitem",
                                "name": "Hey there",
                                "description": "received",
                                "children": [
                                    {"role": "text", "name": "Hey there"},
                                    {"role": "text", "name": "2:00 PM"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    
    mock_page.evaluate = AsyncMock(
        side_effect=[
            inbox_snapshot,           # inbox iter 1 snapshot
            [],                       # inbox iter 1 enrich URLs
            None,                     # inbox scroll JS
            inbox_snapshot,           # inbox iter 2 snapshot
            [],                       # inbox iter 2 enrich URLs (stable → break)
            conversation_snapshot,    # sync_single_conversation initial snapshot
            conversation_snapshot,    # convo scroll-to-top iter 1
            None,                     # convo scroll-to-top JS
            conversation_snapshot,    # convo scroll-to-top iter 2 (stable, break)
        ]
    )

    engine = SyncEngine(
        page=mock_page,
        db=temp_db,
        rate_limiter=mock_rate_limiter,
        notifier=mock_notifier,
    )

    # Execute sync without callback - should work fine
    result = await engine.sync_conversations()
    
    # Verify sync completed successfully
    assert result.conversations_processed == 1
    assert result.messages_stored == 1
    assert result.messages_skipped == 0
    assert len(result.errors) == 0
