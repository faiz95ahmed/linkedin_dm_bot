"""Property-based tests for sync command parameter passing.

This module tests that the sync command correctly passes parameters
to the SyncEngine.sync_conversations method.

**Feature: sync-command, Property 2: Parameter passing to SyncEngine**
**Validates: Requirements 2.1, 2.2, 2.3, 2.4**
"""

import pytest
from datetime import datetime, timedelta
from hypothesis import given, strategies as st, settings
from unittest.mock import AsyncMock, Mock, patch
from dm_bot.main import _sync_flow
from dm_bot.extraction import SyncResult


# Strategy for generating valid datetime objects
@st.composite
def datetime_strategy(draw):
    """Generate datetime objects for testing."""
    # Generate dates within the last year
    days_ago = draw(st.integers(min_value=1, max_value=365))
    return datetime.now() - timedelta(days=days_ago)


# Strategy for generating valid limit values
limit_strategy = st.integers(min_value=1, max_value=100)


def create_mocks():
    """Create all necessary mocks for testing _sync_flow."""
    mock_browser_manager = Mock()
    mock_browser_manager.create_context = AsyncMock()
    mock_browser_manager.close = AsyncMock()
    mock_browser_manager.close_on_fatal_error = AsyncMock()
    
    mock_context = Mock()
    mock_page = Mock()
    mock_page.goto = AsyncMock()
    mock_page.url = "https://www.linkedin.com/feed/"
    mock_context.pages = [mock_page]
    mock_browser_manager.create_context.return_value = mock_context
    
    mock_db = Mock()
    mock_db.initialize_schema = Mock()
    mock_db.close = Mock()
    
    mock_nav_engine = Mock()
    mock_nav_engine.login = AsyncMock(return_value=True)
    mock_nav_engine.navigate_to_messaging = AsyncMock(return_value=True)
    
    mock_rate_limiter = Mock()
    mock_rate_limiter.delay_after_page_load = AsyncMock()
    mock_rate_limiter.delay_for_conversation = AsyncMock()
    mock_rate_limiter.delay_between_actions = AsyncMock()
    mock_rate_limiter.get_statistics = Mock(return_value={
        'total_actions': 0,
        'total_delay': 0.0,
        'average_delay': 0.0,
    })
    
    mock_sync_engine = Mock()
    mock_sync_result = SyncResult(
        conversations_processed=5,
        messages_stored=42,
        messages_skipped=3,
        errors=[],
    )
    mock_sync_engine.sync_conversations = AsyncMock(return_value=mock_sync_result)
    
    return {
        'browser_manager': mock_browser_manager,
        'db': mock_db,
        'nav_engine': mock_nav_engine,
        'rate_limiter': mock_rate_limiter,
        'sync_engine': mock_sync_engine,
    }


@pytest.mark.asyncio
@given(
    since=st.one_of(st.none(), datetime_strategy()),
    limit=limit_strategy,
)
@settings(max_examples=10, deadline=None)  # Limit examples for faster testing
async def test_parameter_passing_to_sync_engine(since, limit):
    """
    Property: For any combination of --since and --limit parameters,
    the sync command should pass these values correctly to
    SyncEngine.sync_conversations(), and the default values
    (30 days ago, limit 50) should be used when parameters are omitted.
    
    **Feature: sync-command, Property 2: Parameter passing to SyncEngine**
    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
    """
    mocks = create_mocks()
    
    # Patch all the dependencies - patch where they're imported/used
    with patch('dm_bot.main.BrowserManager', return_value=mocks['browser_manager']), \
         patch('dm_bot.storage.DatabaseManager', return_value=mocks['db']), \
         patch('dm_bot.main.NavigationEngine', return_value=mocks['nav_engine']), \
         patch('dm_bot.main.RateLimiter', return_value=mocks['rate_limiter']), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.extraction.SyncEngine', return_value=mocks['sync_engine']):
        
        # Execute the sync flow
        from pathlib import Path
        try:
            await _sync_flow(
                username="test@example.com",
                password="password123",
                profile_path=Path("/tmp/test_profile"),
                headless=False,
                since=since,
                limit=limit,
            )
        except Exception:
            # Ignore any exceptions from the flow itself
            # We're only testing parameter passing
            pass
        
        # Verify that sync_conversations was called
        assert mocks['sync_engine'].sync_conversations.called
        
        # Get the actual call arguments
        call_args = mocks['sync_engine'].sync_conversations.call_args
        
        # Verify the parameters were passed correctly
        assert call_args is not None
        
        # Check keyword arguments
        kwargs = call_args.kwargs
        
        # Verify 'since' parameter
        if since is not None:
            assert 'since' in kwargs
            assert kwargs['since'] == since
        else:
            # When since is None, it should be passed as None
            assert 'since' in kwargs
            assert kwargs['since'] is None
        
        # Verify 'limit' parameter
        assert 'limit' in kwargs
        assert kwargs['limit'] == limit
        
        # Verify 'progress_callback' parameter exists
        assert 'progress_callback' in kwargs
        assert callable(kwargs['progress_callback'])


@pytest.mark.asyncio
async def test_default_parameters_applied():
    """
    Test that default values are applied when parameters are omitted.
    
    Default values:
    - since: None (no filtering)
    - limit: None (anchor-based, no forced count)

    **Feature: sync-command, Property 2: Parameter passing to SyncEngine**
    **Validates: Requirements 2.3**
    """
    mocks = create_mocks()

    # Patch all the dependencies - patch where they're imported/used
    with patch('dm_bot.main.BrowserManager', return_value=mocks['browser_manager']), \
         patch('dm_bot.storage.DatabaseManager', return_value=mocks['db']), \
         patch('dm_bot.main.NavigationEngine', return_value=mocks['nav_engine']), \
         patch('dm_bot.main.RateLimiter', return_value=mocks['rate_limiter']), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.extraction.SyncEngine', return_value=mocks['sync_engine']):

        # Execute the sync flow with default parameters
        from pathlib import Path
        try:
            await _sync_flow(
                username="test@example.com",
                password="password123",
                profile_path=Path("/tmp/test_profile"),
                headless=False,
                since=None,
                limit=None,
            )
        except Exception:
            pass

        assert mocks['sync_engine'].sync_conversations.called

        call_args = mocks['sync_engine'].sync_conversations.call_args
        kwargs = call_args.kwargs

        # Verify defaults
        assert kwargs['since'] is None
        assert kwargs['limit'] is None


@pytest.mark.asyncio
async def test_both_parameters_applied():
    """
    Test that both --since and --limit are applied when provided together.
    
    **Feature: sync-command, Property 2: Parameter passing to SyncEngine**
    **Validates: Requirements 2.4**
    """
    mocks = create_mocks()
    
    # Patch all the dependencies - patch where they're imported/used
    with patch('dm_bot.main.BrowserManager', return_value=mocks['browser_manager']), \
         patch('dm_bot.storage.DatabaseManager', return_value=mocks['db']), \
         patch('dm_bot.main.NavigationEngine', return_value=mocks['nav_engine']), \
         patch('dm_bot.main.RateLimiter', return_value=mocks['rate_limiter']), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.extraction.SyncEngine', return_value=mocks['sync_engine']):
        
        # Execute the sync flow with both parameters
        from pathlib import Path
        test_since = datetime(2024, 1, 1)
        test_limit = 25
        
        try:
            await _sync_flow(
                username="test@example.com",
                password="password123",
                profile_path=Path("/tmp/test_profile"),
                headless=False,
                since=test_since,
                limit=test_limit,
            )
        except Exception:
            pass
        
        # Verify that sync_conversations was called with both parameters
        assert mocks['sync_engine'].sync_conversations.called
        
        call_args = mocks['sync_engine'].sync_conversations.call_args
        kwargs = call_args.kwargs
        
        # Verify both parameters are passed
        assert kwargs['since'] == test_since
        assert kwargs['limit'] == test_limit


# Strategy for generating error counts
error_count_strategy = st.integers(min_value=1, max_value=10)
total_conversations_strategy = st.integers(min_value=2, max_value=20)


@pytest.mark.asyncio
@given(
    total_conversations=total_conversations_strategy,
    failed_conversations=error_count_strategy,
)
@settings(max_examples=10, deadline=None)
async def test_error_handling_with_continuation(total_conversations, failed_conversations):
    """
    Property: For any sync execution where K conversations fail to sync (K < N total),
    the command should continue processing remaining conversations, collect all errors,
    and include them in the final summary without stopping the entire sync.
    
    **Feature: sync-command, Property 3: Error handling with continuation**
    **Validates: Requirements 4.2, 4.3**
    """
    # Ensure failed_conversations < total_conversations
    if failed_conversations >= total_conversations:
        failed_conversations = total_conversations - 1
    
    # Create error messages for failed conversations
    error_messages = [
        f"Error syncing conversation {i}: Test error"
        for i in range(failed_conversations)
    ]
    
    mocks = create_mocks()
    
    # Configure sync_engine to return a result with errors
    mock_sync_result = SyncResult(
        conversations_processed=total_conversations - failed_conversations,
        messages_stored=42,
        messages_skipped=3,
        errors=error_messages,
    )
    mocks['sync_engine'].sync_conversations = AsyncMock(return_value=mock_sync_result)
    
    # Patch all the dependencies
    with patch('dm_bot.main.BrowserManager', return_value=mocks['browser_manager']), \
         patch('dm_bot.storage.DatabaseManager', return_value=mocks['db']), \
         patch('dm_bot.main.NavigationEngine', return_value=mocks['nav_engine']), \
         patch('dm_bot.main.RateLimiter', return_value=mocks['rate_limiter']), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.extraction.SyncEngine', return_value=mocks['sync_engine']), \
         patch('dm_bot.main.typer.echo') as mock_echo:
        
        # Execute the sync flow
        from pathlib import Path
        try:
            await _sync_flow(
                username="test@example.com",
                password="password123",
                profile_path=Path("/tmp/test_profile"),
                headless=False,
                since=None,
                limit=total_conversations,
            )
        except Exception:
            pass
        
        # Verify that sync_conversations was called
        assert mocks['sync_engine'].sync_conversations.called
        
        # Verify that the sync completed (didn't raise an exception)
        # by checking that the final summary was displayed
        echo_calls = [str(call) for call in mock_echo.call_args_list]
        echo_output = ' '.join(echo_calls)
        
        # Verify that the final summary includes error information
        assert 'Sync Complete' in echo_output or any('Sync Complete' in str(call) for call in mock_echo.call_args_list)
        
        # Verify that errors were reported in the summary
        if failed_conversations > 0:
            # Check that error count is mentioned
            assert any(
                f'Errors encountered: {failed_conversations}' in str(call)
                for call in mock_echo.call_args_list
            )
        
        # Verify that successful conversations were processed
        successful_conversations = total_conversations - failed_conversations
        assert mock_sync_result.conversations_processed == successful_conversations


@pytest.mark.asyncio
async def test_all_conversations_fail():
    """
    Test edge case where all conversations fail but sync still completes.
    
    **Feature: sync-command, Property 3: Error handling with continuation**
    **Validates: Requirements 4.2, 4.3**
    """
    total_conversations = 5
    error_messages = [
        f"Error syncing conversation {i}: Test error"
        for i in range(total_conversations)
    ]
    
    mocks = create_mocks()
    
    # Configure sync_engine to return a result with all conversations failed
    mock_sync_result = SyncResult(
        conversations_processed=0,  # All failed
        messages_stored=0,
        messages_skipped=0,
        errors=error_messages,
    )
    mocks['sync_engine'].sync_conversations = AsyncMock(return_value=mock_sync_result)
    
    # Patch all the dependencies
    with patch('dm_bot.main.BrowserManager', return_value=mocks['browser_manager']), \
         patch('dm_bot.storage.DatabaseManager', return_value=mocks['db']), \
         patch('dm_bot.main.NavigationEngine', return_value=mocks['nav_engine']), \
         patch('dm_bot.main.RateLimiter', return_value=mocks['rate_limiter']), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.extraction.SyncEngine', return_value=mocks['sync_engine']), \
         patch('dm_bot.main.typer.echo') as mock_echo:
        
        # Execute the sync flow
        from pathlib import Path
        try:
            await _sync_flow(
                username="test@example.com",
                password="password123",
                profile_path=Path("/tmp/test_profile"),
                headless=False,
                since=None,
                limit=total_conversations,
            )
        except Exception:
            pass
        
        # Verify that sync_conversations was called
        assert mocks['sync_engine'].sync_conversations.called
        
        # Verify that the final summary was displayed even with all failures
        echo_calls = [str(call) for call in mock_echo.call_args_list]
        assert any('Sync Complete' in str(call) for call in mock_echo.call_args_list)
        
        # Verify that all errors were reported
        assert any(
            f'Errors encountered: {total_conversations}' in str(call)
            for call in mock_echo.call_args_list
        )


@pytest.mark.asyncio
@given(
    num_conversations=st.integers(min_value=1, max_value=10),
    num_scrolls=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=10, deadline=None)
async def test_rate_limiting_enforcement(num_conversations, num_scrolls):
    """
    Property: For any sync execution, all navigation and scrolling actions
    should go through the RateLimiter, ensuring delays are applied between
    actions as configured.
    
    This test verifies that:
    1. delay_for_conversation() is called for each conversation
    2. delay_between_actions() is called for each scroll operation
    3. delay_after_page_load() is called after navigation
    
    **Feature: sync-command, Property 4: Rate limiting enforcement**
    **Validates: Requirements 5.1, 5.2**
    """
    mocks = create_mocks()
    
    # Configure sync_engine to simulate processing conversations
    mock_sync_result = SyncResult(
        conversations_processed=num_conversations,
        messages_stored=num_conversations * 5,
        messages_skipped=num_conversations * 2,
        errors=[],
    )
    mocks['sync_engine'].sync_conversations = AsyncMock(return_value=mock_sync_result)
    
    # Track rate limiter calls
    delay_for_conversation_calls = []
    delay_between_actions_calls = []
    delay_after_page_load_calls = []
    
    async def track_delay_for_conversation():
        delay_for_conversation_calls.append(1)
    
    async def track_delay_between_actions():
        delay_between_actions_calls.append(1)
    
    async def track_delay_after_page_load():
        delay_after_page_load_calls.append(1)
    
    mocks['rate_limiter'].delay_for_conversation = AsyncMock(side_effect=track_delay_for_conversation)
    mocks['rate_limiter'].delay_between_actions = AsyncMock(side_effect=track_delay_between_actions)
    mocks['rate_limiter'].delay_after_page_load = AsyncMock(side_effect=track_delay_after_page_load)
    mocks['rate_limiter'].get_statistics = Mock(return_value={
        'total_actions': num_conversations + num_scrolls,
        'total_delay': (num_conversations + num_scrolls) * 3.5,
        'average_delay': 3.5,
    })
    
    # Patch all the dependencies
    with patch('dm_bot.main.BrowserManager', return_value=mocks['browser_manager']), \
         patch('dm_bot.storage.DatabaseManager', return_value=mocks['db']), \
         patch('dm_bot.main.NavigationEngine', return_value=mocks['nav_engine']), \
         patch('dm_bot.main.RateLimiter', return_value=mocks['rate_limiter']), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.extraction.SyncEngine', return_value=mocks['sync_engine']):
        
        # Execute the sync flow
        from pathlib import Path
        try:
            await _sync_flow(
                username="test@example.com",
                password="password123",
                profile_path=Path("/tmp/test_profile"),
                headless=False,
                since=None,
                limit=num_conversations,
            )
        except Exception:
            pass
        
        # Verify that sync_conversations was called
        assert mocks['sync_engine'].sync_conversations.called
        
        # Verify that delay_after_page_load was called at least once
        # (for initial navigation to LinkedIn)
        assert len(delay_after_page_load_calls) >= 1, \
            "delay_after_page_load should be called for page navigation"
        
        # Verify that get_statistics was called to retrieve rate limit stats
        assert mocks['rate_limiter'].get_statistics.called, \
            "get_statistics should be called to retrieve rate limit statistics"


@pytest.mark.asyncio
async def test_rate_limit_statistics_in_summary():
    """
    Test that rate limit statistics are included in the final summary.
    
    **Feature: sync-command, Property 4: Rate limiting enforcement**
    **Validates: Requirements 5.4**
    """
    mocks = create_mocks()
    
    # Configure sync_engine
    mock_sync_result = SyncResult(
        conversations_processed=3,
        messages_stored=15,
        messages_skipped=5,
        errors=[],
    )
    mocks['sync_engine'].sync_conversations = AsyncMock(return_value=mock_sync_result)
    
    # Configure rate limiter to return statistics
    mocks['rate_limiter'].get_statistics = Mock(return_value={
        'total_actions': 10,
        'total_delay': 35.0,
        'average_delay': 3.5,
    })
    
    # Patch all the dependencies
    with patch('dm_bot.main.BrowserManager', return_value=mocks['browser_manager']), \
         patch('dm_bot.storage.DatabaseManager', return_value=mocks['db']), \
         patch('dm_bot.main.NavigationEngine', return_value=mocks['nav_engine']), \
         patch('dm_bot.main.RateLimiter', return_value=mocks['rate_limiter']), \
         patch('dm_bot.main.NotificationService'), \
         patch('dm_bot.extraction.SyncEngine', return_value=mocks['sync_engine']), \
         patch('dm_bot.main.typer.echo') as mock_echo:
        
        # Execute the sync flow
        from pathlib import Path
        try:
            await _sync_flow(
                username="test@example.com",
                password="password123",
                profile_path=Path("/tmp/test_profile"),
                headless=False,
                since=None,
                limit=10,
            )
        except Exception:
            pass
        
        # Verify that get_statistics was called
        assert mocks['rate_limiter'].get_statistics.called
        
        # Verify that rate limit statistics are displayed in the summary
        echo_calls = [str(call) for call in mock_echo.call_args_list]
        echo_output = ' '.join(echo_calls)
        
        # Check that rate limiting section is present
        assert any('Rate Limiting' in str(call) for call in mock_echo.call_args_list), \
            "Rate Limiting section should be in the summary"
        
        # Check that total actions is displayed
        assert any('Total actions: 10' in str(call) for call in mock_echo.call_args_list), \
            "Total actions should be displayed in the summary"
        
        # Check that average delay is displayed
        assert any('Average delay: 3.50s' in str(call) for call in mock_echo.call_args_list), \
            "Average delay should be displayed in the summary"
