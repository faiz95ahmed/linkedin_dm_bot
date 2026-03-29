"""Tests for browser manager."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from hypothesis import given, strategies as st, settings

from dm_bot.browser import BrowserManager
from dm_bot.config import VIEWPORT_WIDTH, VIEWPORT_HEIGHT, USER_AGENT


@pytest.mark.asyncio
async def test_browser_manager_initialization():
    """Test that BrowserManager can be initialized."""
    manager = BrowserManager()
    assert manager.playwright is None
    assert manager.browser is None
    assert manager.context is None


@pytest.mark.asyncio
async def test_browser_manager_create_context(tmp_path):
    """Test that create_context creates a browser context with correct configuration."""
    manager = BrowserManager()
    
    # Use temporary directory for profile
    profile_path = tmp_path / "test_profile"
    
    try:
        # Create context
        context = await manager.create_context(
            profile_path=profile_path,
            headless=True
        )
        
        # Verify context was created
        assert context is not None
        assert manager.context is not None
        assert manager.playwright is not None
        
        # Verify profile directory was created
        assert profile_path.exists()
        assert profile_path.is_dir()
        
        # Create a page to verify viewport and user agent
        page = await context.new_page()
        
        # Verify viewport dimensions
        viewport = page.viewport_size
        assert viewport["width"] == VIEWPORT_WIDTH
        assert viewport["height"] == VIEWPORT_HEIGHT
        
        # Verify user agent
        user_agent = await page.evaluate("navigator.userAgent")
        assert user_agent == USER_AGENT
        
        await page.close()
        
    finally:
        # Clean up
        await manager.close()
        
        # Verify cleanup
        assert manager.context is None
        assert manager.playwright is None


@pytest.mark.asyncio
async def test_browser_manager_close():
    """Test that close() properly cleans up resources."""
    manager = BrowserManager()
    
    # Create context
    profile_path = Path("/tmp/test_browser_close")
    profile_path.mkdir(parents=True, exist_ok=True)
    
    try:
        await manager.create_context(profile_path=profile_path, headless=True)
        
        # Verify resources are allocated
        assert manager.context is not None
        assert manager.playwright is not None
        
        # Close
        await manager.close()
        
        # Verify resources are cleaned up
        assert manager.context is None
        assert manager.playwright is None
        
    finally:
        # Ensure cleanup even if test fails
        if manager.context or manager.playwright:
            await manager.close()


# Feature: linkedin-navigation, Property 9: Clean browser context closure on fatal errors
# Validates: Requirements 5.5
@settings(max_examples=100, deadline=None)
@given(
    error_message=st.text(min_size=1, max_size=100),
)
def test_property_9_clean_browser_closure_on_fatal_error(
    error_message: str,
) -> None:
    """
    Property 9: Clean browser context closure on fatal errors
    
    For any fatal error, the system should close the browser context cleanly
    before exiting.
    
    This test verifies:
    1. close() is called on the browser context
    2. stop() is called on the playwright instance
    3. Errors during cleanup are logged but don't crash
    """
    import asyncio
    from dm_bot.browser import BrowserManager
    from dm_bot.actions import FatalError
    
    async def run_test():
        # Create browser manager
        manager = BrowserManager()
        
        # Mock context and playwright
        mock_context = AsyncMock()
        mock_playwright = AsyncMock()
        
        manager.context = mock_context
        manager.playwright = mock_playwright
        
        # Create a fatal error
        error = FatalError(error_message)
        
        # Call close_on_fatal_error
        await manager.close_on_fatal_error(error)
        
        # Verify context.close() was called
        assert mock_context.close.called, (
            "Browser context close() should be called on fatal error"
        )
        
        # Verify playwright.stop() was called
        assert mock_playwright.stop.called, (
            "Playwright stop() should be called on fatal error"
        )
        
        # Verify context and playwright are set to None
        assert manager.context is None, (
            "Browser context should be set to None after cleanup"
        )
        
        assert manager.playwright is None, (
            "Playwright should be set to None after cleanup"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 9: Clean browser context closure on fatal errors
# Validates: Requirements 5.5
@settings(max_examples=100, deadline=None)
@given(
    error_message=st.text(min_size=1, max_size=100),
)
def test_property_9_cleanup_resilient_to_errors(
    error_message: str,
) -> None:
    """
    Property 9: Clean browser context closure on fatal errors
    
    Verifies that cleanup continues even if context.close() or playwright.stop()
    raise exceptions. The system should log errors but not crash.
    """
    import asyncio
    from dm_bot.browser import BrowserManager
    from dm_bot.actions import FatalError
    
    async def run_test():
        # Create browser manager
        manager = BrowserManager()
        
        # Mock context and playwright that raise errors on close/stop
        mock_context = AsyncMock()
        mock_context.close.side_effect = Exception("Context close failed")
        
        mock_playwright = AsyncMock()
        mock_playwright.stop.side_effect = Exception("Playwright stop failed")
        
        manager.context = mock_context
        manager.playwright = mock_playwright
        
        # Create a fatal error
        error = FatalError(error_message)
        
        # Call close_on_fatal_error - should not raise
        try:
            await manager.close_on_fatal_error(error)
        except Exception as e:
            assert False, (
                f"close_on_fatal_error should not raise exceptions, "
                f"but raised {type(e).__name__}: {e}"
            )
        
        # Verify both close and stop were attempted
        assert mock_context.close.called, (
            "Context close() should be attempted even if it fails"
        )
        
        assert mock_playwright.stop.called, (
            "Playwright stop() should be attempted even if context close fails"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 9: Clean browser context closure on fatal errors
# Validates: Requirements 5.5
def test_property_9_close_is_idempotent() -> None:
    """
    Property 9: Clean browser context closure on fatal errors
    
    Verifies that close() can be called multiple times safely without errors.
    This is important for cleanup in error scenarios.
    """
    import asyncio
    from dm_bot.browser import BrowserManager
    
    async def run_test():
        # Create browser manager
        manager = BrowserManager()
        
        # Mock context and playwright
        mock_context = AsyncMock()
        mock_playwright = AsyncMock()
        
        manager.context = mock_context
        manager.playwright = mock_playwright
        
        # Call close() multiple times
        await manager.close()
        await manager.close()
        await manager.close()
        
        # Verify close was called at least once
        assert mock_context.close.called, (
            "Context close() should be called"
        )
        
        # Verify no exceptions were raised
        # (test passes if we get here)
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 9: Clean browser context closure on fatal errors
# Validates: Requirements 5.5
@settings(max_examples=100, deadline=None)
@given(
    has_context=st.booleans(),
    has_playwright=st.booleans(),
)
def test_property_9_close_handles_partial_initialization(
    has_context: bool,
    has_playwright: bool,
) -> None:
    """
    Property 9: Clean browser context closure on fatal errors
    
    Verifies that close() handles cases where context or playwright
    may not be initialized (None).
    """
    import asyncio
    from dm_bot.browser import BrowserManager
    
    async def run_test():
        # Create browser manager
        manager = BrowserManager()
        
        # Set context and playwright based on test parameters
        if has_context:
            manager.context = AsyncMock()
        else:
            manager.context = None
        
        if has_playwright:
            manager.playwright = AsyncMock()
        else:
            manager.playwright = None
        
        # Call close() - should not raise
        try:
            await manager.close()
        except Exception as e:
            assert False, (
                f"close() should handle None context/playwright gracefully, "
                f"but raised {type(e).__name__}: {e}"
            )
        
        # Verify context and playwright are None after close
        assert manager.context is None, (
            "Context should be None after close"
        )
        
        assert manager.playwright is None, (
            "Playwright should be None after close"
        )
    
    asyncio.run(run_test())
