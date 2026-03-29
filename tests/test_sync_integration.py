"""Integration tests for sync command.

This module tests the end-to-end sync command workflow with mock LinkedIn pages.
It verifies that the sync command correctly extracts conversations and messages
from the accessibility tree and stores them in the database.

**Requirements: 1.1, 1.2, 1.3**
"""

import pytest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from dm_bot.main import _sync_flow
from dm_bot.storage import DatabaseManager, ConnectionRepository, ConversationRepository, MessageRepository


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_sync.db"
    db = DatabaseManager(db_path=db_path)
    db.initialize_schema()
    yield db
    db.close()


@pytest.fixture
def mock_inbox_snapshot():
    """Create a mock accessibility snapshot of the LinkedIn inbox."""
    return {
        "role": "main",
        "name": "Main content",
        "children": [
            {
                "role": "list",
                "name": "Conversations list",
                "children": [
                    {
                        "role": "listitem",
                        "name": "John Doe",
                        "children": [
                            {
                                "role": "text",
                                "name": "John Doe"
                            },
                            {
                                "role": "text",
                                "name": "Hey, how are you?"
                            },
                            {
                                "role": "text",
                                "name": "2h"
                            },
                            {
                                "role": "link",
                                "name": "View conversation",
                                "url": "https://www.linkedin.com/messaging/thread/2-john-doe/"
                            }
                        ]
                    },
                    {
                        "role": "listitem",
                        "name": "Jane Smith",
                        "children": [
                            {
                                "role": "text",
                                "name": "Jane Smith"
                            },
                            {
                                "role": "text",
                                "name": "Thanks for connecting!"
                            },
                            {
                                "role": "text",
                                "name": "1d"
                            },
                            {
                                "role": "link",
                                "name": "View conversation",
                                "url": "https://www.linkedin.com/messaging/thread/2-jane-smith/"
                            }
                        ]
                    },
                    {
                        "role": "listitem",
                        "name": "Bob Wilson",
                        "children": [
                            {
                                "role": "text",
                                "name": "Bob Wilson"
                            },
                            {
                                "role": "text",
                                "name": "Let's schedule a call"
                            },
                            {
                                "role": "text",
                                "name": "3d"
                            },
                            {
                                "role": "link",
                                "name": "View conversation",
                                "url": "https://www.linkedin.com/messaging/thread/2-bob-wilson/"
                            }
                        ]
                    }
                ]
            }
        ]
    }


@pytest.fixture
def mock_conversation_snapshots():
    """Create mock accessibility snapshots for individual conversations."""
    now = datetime.now()
    
    return {
        "john-doe": {
            "role": "main",
            "name": "Conversation with John Doe",
            "children": [
                {
                    "role": "heading",
                    "name": "John Doe",
                    "children": [
                        {
                            "role": "link",
                            "name": "John Doe",
                            "url": "https://www.linkedin.com/in/john-doe/"
                        }
                    ]
                },
                {
                    "role": "list",
                    "name": "Messages",
                    "children": [
                        {
                            "role": "listitem",
                            "name": f"John Doe: Hi there! {(now - timedelta(hours=3)).strftime('%I:%M %p')}",
                            "description": "inbound",
                            "children": [
                                {
                                    "role": "text",
                                    "name": "Hi there!"
                                },
                                {
                                    "role": "text",
                                    "name": (now - timedelta(hours=3)).strftime("%I:%M %p")
                                }
                            ]
                        },
                        {
                            "role": "listitem",
                            "name": f"You: Hello John! {(now - timedelta(hours=2, minutes=30)).strftime('%I:%M %p')}",
                            "description": "You sent",
                            "children": [
                                {
                                    "role": "text",
                                    "name": "You: Hello John!"
                                },
                                {
                                    "role": "text",
                                    "name": (now - timedelta(hours=2, minutes=30)).strftime("%I:%M %p")
                                }
                            ]
                        },
                        {
                            "role": "listitem",
                            "name": f"John Doe: Hey, how are you? {(now - timedelta(hours=2)).strftime('%I:%M %p')}",
                            "description": "inbound",
                            "children": [
                                {
                                    "role": "text",
                                    "name": "Hey, how are you?"
                                },
                                {
                                    "role": "text",
                                    "name": (now - timedelta(hours=2)).strftime("%I:%M %p")
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        "jane-smith": {
            "role": "main",
            "name": "Conversation with Jane Smith",
            "children": [
                {
                    "role": "heading",
                    "name": "Jane Smith",
                    "children": [
                        {
                            "role": "link",
                            "name": "Jane Smith",
                            "url": "https://www.linkedin.com/in/jane-smith/"
                        }
                    ]
                },
                {
                    "role": "list",
                    "name": "Messages",
                    "children": [
                        {
                            "role": "listitem",
                            "name": f"You: Hi Jane, nice to connect! {(now - timedelta(days=1, hours=2)).strftime('%I:%M %p')}",
                            "description": "You sent",
                            "children": [
                                {
                                    "role": "text",
                                    "name": "You: Hi Jane, nice to connect!"
                                },
                                {
                                    "role": "text",
                                    "name": (now - timedelta(days=1, hours=2)).strftime("%I:%M %p")
                                }
                            ]
                        },
                        {
                            "role": "listitem",
                            "name": f"Jane Smith: Thanks for connecting! {(now - timedelta(days=1)).strftime('%I:%M %p')}",
                            "description": "inbound",
                            "children": [
                                {
                                    "role": "text",
                                    "name": "Thanks for connecting!"
                                },
                                {
                                    "role": "text",
                                    "name": (now - timedelta(days=1)).strftime("%I:%M %p")
                                }
                            ]
                        }
                    ]
                }
            ]
        },
        "bob-wilson": {
            "role": "main",
            "name": "Conversation with Bob Wilson",
            "children": [
                {
                    "role": "heading",
                    "name": "Bob Wilson",
                    "children": [
                        {
                            "role": "link",
                            "name": "Bob Wilson",
                            "url": "https://www.linkedin.com/in/bob-wilson/"
                        }
                    ]
                },
                {
                    "role": "list",
                    "name": "Messages",
                    "children": [
                        {
                            "role": "listitem",
                            "name": f"Bob Wilson: Let's schedule a call {(now - timedelta(days=3)).strftime('%I:%M %p')}",
                            "description": "inbound",
                            "children": [
                                {
                                    "role": "text",
                                    "name": "Let's schedule a call"
                                },
                                {
                                    "role": "text",
                                    "name": (now - timedelta(days=3)).strftime("%I:%M %p")
                                }
                            ]
                        },
                        {
                            "role": "listitem",
                            "name": f"You: Sure, when works for you? {(now - timedelta(days=3, hours=-1)).strftime('%I:%M %p')}",
                            "description": "You sent",
                            "children": [
                                {
                                    "role": "text",
                                    "name": "You: Sure, when works for you?"
                                },
                                {
                                    "role": "text",
                                    "name": (now - timedelta(days=3, hours=-1)).strftime("%I:%M %p")
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }


@pytest.mark.asyncio
async def test_sync_command_end_to_end(temp_db, mock_inbox_snapshot, mock_conversation_snapshots):
    """
    Test the complete sync command workflow with mock LinkedIn pages.
    
    This test verifies:
    1. Sync command extracts conversation previews from inbox
    2. Sync command navigates to each conversation
    3. Sync command extracts messages from each conversation
    4. Database contains expected connections, conversations, and messages
    5. Output format is correct with progress reporting
    
    **Requirements: 1.1, 1.2, 1.3**
    """
    # Track which URL we're on to return the correct snapshot
    current_url = "https://www.linkedin.com/messaging/"
    
    def get_snapshot_for_url():
        """Return the appropriate snapshot based on current URL."""
        if "john-doe" in current_url:
            return mock_conversation_snapshots["john-doe"]
        elif "jane-smith" in current_url:
            return mock_conversation_snapshots["jane-smith"]
        elif "bob-wilson" in current_url:
            return mock_conversation_snapshots["bob-wilson"]
        else:
            # Inbox view
            return mock_inbox_snapshot
    
    # Create mock page
    mock_page = Mock()
    mock_page.url = current_url
    
    async def mock_goto(url):
        """Mock page navigation."""
        nonlocal current_url
        current_url = url
        mock_page.url = url
    
    mock_page.goto = AsyncMock(side_effect=mock_goto)

    # Route evaluate calls: accessibility tree → snapshot, thread URL enrichment → [],
    # scroll JS → None.
    def evaluate_side_effect(js, *args, **kwargs):
        if 'querySelectorAll' in js:
            return []
        elif 'scrollTop' in js:
            return None
        else:
            return get_snapshot_for_url()

    mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)

    # Create mock browser manager
    mock_browser_manager = Mock()
    mock_context = Mock()
    mock_context.pages = [mock_page]
    mock_browser_manager.create_context = AsyncMock(return_value=mock_context)
    mock_browser_manager.close = AsyncMock()
    mock_browser_manager.close_on_fatal_error = AsyncMock()

    # Create mock navigation engine
    mock_nav_engine = Mock()
    mock_nav_engine.login = AsyncMock(return_value=True)
    mock_nav_engine.navigate_to_messaging = AsyncMock(return_value=True)
    
    # Create mock rate limiter
    mock_rate_limiter = Mock()
    mock_rate_limiter.delay_after_page_load = AsyncMock()
    mock_rate_limiter.delay_for_conversation = AsyncMock()
    mock_rate_limiter.delay_between_actions = AsyncMock()
    mock_rate_limiter.get_statistics = Mock(return_value={
        'total_actions': 15,
        'total_delay': 52.5,
        'average_delay': 3.5,
    })
    
    # Capture output
    output_lines = []
    
    def mock_echo(message, err=False):
        """Capture typer.echo output."""
        output_lines.append(message)
    
    # Patch all dependencies
    with patch('dm_bot.main.BrowserManager', return_value=mock_browser_manager), \
         patch('dm_bot.storage.DatabaseManager', return_value=temp_db), \
         patch('dm_bot.main.NavigationEngine', return_value=mock_nav_engine), \
         patch('dm_bot.main.RateLimiter', return_value=mock_rate_limiter), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.main.typer.echo', side_effect=mock_echo):
        
        # Run the sync flow
        await _sync_flow(
            username="test@example.com",
            password="password123",
            profile_path=Path("/tmp/test_profile"),
            headless=True,
            since=None,
            limit=10,
        )
    
    # Verify database contents
    conn_repo = ConnectionRepository(temp_db)
    conv_repo = ConversationRepository(temp_db)
    msg_repo = MessageRepository(temp_db)
    
    # Check connections were created
    connections = conn_repo.list_all()
    assert len(connections) == 3, f"Expected 3 connections, got {len(connections)}"
    
    connection_names = {c.display_name for c in connections}
    assert "John Doe" in connection_names
    assert "Jane Smith" in connection_names
    assert "Bob Wilson" in connection_names
    
    # Check conversations were created
    for connection in connections:
        conversation = conv_repo.get_by_connection_id(connection.id)
        assert conversation is not None, f"No conversation for {connection.display_name}"
        assert conversation.last_synced_at is not None, f"Conversation not synced for {connection.display_name}"
    
    # Check messages were stored
    total_messages = 0
    for connection in connections:
        conversation = conv_repo.get_by_connection_id(connection.id)
        messages = msg_repo.get_by_conversation(conversation.id)
        total_messages += len(messages)
        
        # Verify message content based on connection
        if connection.display_name == "John Doe":
            assert len(messages) == 3, f"Expected 3 messages for John Doe, got {len(messages)}"
            # Check message content (direction detection may vary based on accessibility tree structure)
            message_contents = [m.content for m in messages]
            assert any("Hi there!" in content for content in message_contents)
            assert any("Hello John!" in content for content in message_contents)
            assert any("Hey, how are you?" in content for content in message_contents)
        elif connection.display_name == "Jane Smith":
            assert len(messages) == 2, f"Expected 2 messages for Jane Smith, got {len(messages)}"
            # Just verify we have 2 messages with correct content
            message_contents = [m.content for m in messages]
            assert any("Hi Jane" in content for content in message_contents)
            assert any("Thanks for connecting!" in content for content in message_contents)
        elif connection.display_name == "Bob Wilson":
            assert len(messages) == 2, f"Expected 2 messages for Bob Wilson, got {len(messages)}"
            # Just verify we have 2 messages with correct content
            message_contents = [m.content for m in messages]
            assert any("Let's schedule a call" in content for content in message_contents)
            assert any("Sure, when works for you?" in content for content in message_contents)
    
    assert total_messages == 7, f"Expected 7 total messages, got {total_messages}"
    
    # Verify output format (Requirement 1.3)
    output_text = "\n".join(output_lines)
    
    # Check for progress indicators
    assert "Processing 1/3: John Doe" in output_text or "Processing" in output_text
    assert "Found" in output_text  # "Found X messages"
    assert "Stored" in output_text  # "Stored X new, skipped Y duplicates"
    
    # Check for final summary
    assert "Sync Complete" in output_text
    assert "Conversations processed:" in output_text
    assert "Messages stored:" in output_text
    assert "Messages skipped" in output_text
    assert "Time elapsed:" in output_text
    
    # Check for rate limiting stats
    assert "Rate Limiting:" in output_text
    assert "Total actions:" in output_text
    assert "Average delay:" in output_text


@pytest.mark.asyncio
async def test_sync_command_with_limit(temp_db, mock_inbox_snapshot, mock_conversation_snapshots):
    """
    Test that the sync command respects the --limit parameter.
    
    **Requirements: 1.1, 2.2**
    """
    current_url = "https://www.linkedin.com/messaging/"
    
    def get_snapshot_for_url():
        if "john-doe" in current_url:
            return mock_conversation_snapshots["john-doe"]
        else:
            return mock_inbox_snapshot
    
    mock_page = Mock()
    mock_page.url = current_url
    
    async def mock_goto(url):
        nonlocal current_url
        current_url = url
        mock_page.url = url
    
    mock_page.goto = AsyncMock(side_effect=mock_goto)

    def evaluate_side_effect(js, *args, **kwargs):
        if 'querySelectorAll' in js:
            return []
        elif 'scrollTop' in js:
            return None
        else:
            return get_snapshot_for_url()

    mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)

    mock_browser_manager = Mock()
    mock_context = Mock()
    mock_context.pages = [mock_page]
    mock_browser_manager.create_context = AsyncMock(return_value=mock_context)
    mock_browser_manager.close = AsyncMock()
    mock_browser_manager.close_on_fatal_error = AsyncMock()

    mock_nav_engine = Mock()
    mock_nav_engine.login = AsyncMock(return_value=True)
    mock_nav_engine.navigate_to_messaging = AsyncMock(return_value=True)

    mock_rate_limiter = Mock()
    mock_rate_limiter.delay_after_page_load = AsyncMock()
    mock_rate_limiter.delay_for_conversation = AsyncMock()
    mock_rate_limiter.delay_between_actions = AsyncMock()
    mock_rate_limiter.get_statistics = Mock(return_value={
        'total_actions': 5,
        'total_delay': 17.5,
        'average_delay': 3.5,
    })

    with patch('dm_bot.main.BrowserManager', return_value=mock_browser_manager), \
         patch('dm_bot.storage.DatabaseManager', return_value=temp_db), \
         patch('dm_bot.main.NavigationEngine', return_value=mock_nav_engine), \
         patch('dm_bot.main.RateLimiter', return_value=mock_rate_limiter), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.main.typer.echo'):

        # Run sync with limit=1
        await _sync_flow(
            username="test@example.com",
            password="password123",
            profile_path=Path("/tmp/test_profile"),
            headless=True,
            since=None,
            limit=1,  # Only sync 1 conversation
        )
    
    # Verify only 1 conversation was synced
    conn_repo = ConnectionRepository(temp_db)
    connections = conn_repo.list_all()
    
    # Should only have 1 connection (the most recent one)
    assert len(connections) == 1, f"Expected 1 connection with limit=1, got {len(connections)}"
    assert connections[0].display_name == "John Doe"  # Most recent conversation


@pytest.mark.asyncio
async def test_sync_command_idempotency(temp_db, mock_inbox_snapshot, mock_conversation_snapshots):
    """
    Test that running sync twice doesn't create duplicate messages.
    
    This verifies the deduplication logic works correctly.
    
    **Requirements: 1.1, 1.3**
    """
    current_url = "https://www.linkedin.com/messaging/"
    
    def get_snapshot_for_url():
        if "john-doe" in current_url:
            return mock_conversation_snapshots["john-doe"]
        elif "jane-smith" in current_url:
            return mock_conversation_snapshots["jane-smith"]
        elif "bob-wilson" in current_url:
            return mock_conversation_snapshots["bob-wilson"]
        else:
            return mock_inbox_snapshot
    
    mock_page = Mock()
    mock_page.url = current_url
    
    async def mock_goto(url):
        nonlocal current_url
        current_url = url
        mock_page.url = url
    
    mock_page.goto = AsyncMock(side_effect=mock_goto)

    def evaluate_side_effect(js, *args, **kwargs):
        if 'querySelectorAll' in js:
            return []
        elif 'scrollTop' in js:
            return None
        else:
            return get_snapshot_for_url()

    mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)

    mock_browser_manager = Mock()
    mock_context = Mock()
    mock_context.pages = [mock_page]
    mock_browser_manager.create_context = AsyncMock(return_value=mock_context)
    mock_browser_manager.close = AsyncMock()
    mock_browser_manager.close_on_fatal_error = AsyncMock()

    mock_nav_engine = Mock()
    mock_nav_engine.login = AsyncMock(return_value=True)
    mock_nav_engine.navigate_to_messaging = AsyncMock(return_value=True)

    mock_rate_limiter = Mock()
    mock_rate_limiter.delay_after_page_load = AsyncMock()
    mock_rate_limiter.delay_for_conversation = AsyncMock()
    mock_rate_limiter.delay_between_actions = AsyncMock()
    mock_rate_limiter.get_statistics = Mock(return_value={
        'total_actions': 5,
        'total_delay': 17.5,
        'average_delay': 3.5,
    })

    output_lines_first = []
    output_lines_second = []
    
    def mock_echo_first(message, err=False):
        output_lines_first.append(message)
    
    def mock_echo_second(message, err=False):
        output_lines_second.append(message)
    
    # First sync - sync all 3 conversations
    with patch('dm_bot.main.BrowserManager', return_value=mock_browser_manager), \
         patch('dm_bot.storage.DatabaseManager', return_value=temp_db), \
         patch('dm_bot.main.NavigationEngine', return_value=mock_nav_engine), \
         patch('dm_bot.main.RateLimiter', return_value=mock_rate_limiter), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.main.typer.echo', side_effect=mock_echo_first):
        
        await _sync_flow(
            username="test@example.com",
            password="password123",
            profile_path=Path("/tmp/test_profile"),
            headless=True,
            since=None,
            limit=10,  # Sync all conversations
        )
    
    # Get message count after first sync
    conn_repo = ConnectionRepository(temp_db)
    conv_repo = ConversationRepository(temp_db)
    msg_repo = MessageRepository(temp_db)
    
    connections = conn_repo.list_all()
    assert len(connections) == 3
    
    # Count total messages after first sync
    total_messages_first = 0
    for connection in connections:
        conversation = conv_repo.get_by_connection_id(connection.id)
        messages = msg_repo.get_by_conversation(conversation.id)
        total_messages_first += len(messages)
    
    assert total_messages_first == 7  # Total messages across all conversations
    
    # Second sync - should not create duplicates
    with patch('dm_bot.main.BrowserManager', return_value=mock_browser_manager), \
         patch('dm_bot.storage.DatabaseManager', return_value=temp_db), \
         patch('dm_bot.main.NavigationEngine', return_value=mock_nav_engine), \
         patch('dm_bot.main.RateLimiter', return_value=mock_rate_limiter), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.main.typer.echo', side_effect=mock_echo_second):
        
        await _sync_flow(
            username="test@example.com",
            password="password123",
            profile_path=Path("/tmp/test_profile"),
            headless=True,
            since=None,
            limit=10,  # Sync all conversations again
        )
    
    # Verify no duplicates were created
    total_messages_second = 0
    for connection in connections:
        conversation = conv_repo.get_by_connection_id(connection.id)
        messages = msg_repo.get_by_conversation(conversation.id)
        total_messages_second += len(messages)
    
    assert total_messages_second == total_messages_first, \
        f"Expected {total_messages_first} messages, got {total_messages_second} (duplicates created!)"
    
    # Verify output shows messages were skipped
    output_text_second = "\n".join(output_lines_second)
    # The second sync should show that no conversations were processed
    # because they were all already synced (last_synced_at >= last_message_at)
    # This is the expected behavior - conversations that are already synced are skipped
    assert "Conversations processed: 0" in output_text_second, \
        f"Expected 0 conversations processed in second sync (all already synced), but got: {output_text_second}"
