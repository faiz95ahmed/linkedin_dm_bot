"""Integration tests for browser manager.

These tests verify that the BrowserManager correctly configures
the browser with the required mobile viewport and user agent.
"""

import pytest
from pathlib import Path
from dm_bot.browser import BrowserManager
from dm_bot.config import VIEWPORT_WIDTH, VIEWPORT_HEIGHT, USER_AGENT


@pytest.mark.asyncio
async def test_browser_manager_basic_functionality():
    """
    Test basic browser manager functionality.
    
    Verifies:
    - BrowserManager can be instantiated
    - create_context() returns a valid context
    - close() cleans up resources properly
    """
    manager = BrowserManager()
    
    # Initially, no resources should be allocated
    assert manager.playwright is None
    assert manager.context is None
    
    # Create a temporary profile directory
    profile_path = Path("/tmp/test_browser_basic")
    profile_path.mkdir(parents=True, exist_ok=True)
    
    try:
        # Create context - this will launch the browser
        context = await manager.create_context(
            profile_path=profile_path,
            headless=True
        )
        
        # Verify context was created
        assert context is not None
        assert manager.context is not None
        assert manager.playwright is not None
        
        # Verify we can create a page
        page = await context.new_page()
        assert page is not None
        
        await page.close()
        
    finally:
        # Clean up
        await manager.close()
        
        # Verify cleanup
        assert manager.context is None
        assert manager.playwright is None


@pytest.mark.asyncio
async def test_browser_viewport_configuration():
    """
    Test that browser viewport is correctly configured.
    
    Requirements: 1.3 - Mobile viewport (320×568)
    """
    manager = BrowserManager()
    profile_path = Path("/tmp/test_browser_viewport")
    profile_path.mkdir(parents=True, exist_ok=True)
    
    try:
        context = await manager.create_context(
            profile_path=profile_path,
            headless=True
        )
        
        page = await context.new_page()
        
        # Check viewport dimensions
        viewport = page.viewport_size
        assert viewport is not None
        assert viewport["width"] == VIEWPORT_WIDTH
        assert viewport["height"] == VIEWPORT_HEIGHT
        assert viewport["width"] == 320
        assert viewport["height"] == 568
        
        await page.close()
        
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_browser_user_agent_configuration():
    """
    Test that browser user agent is correctly configured.
    
    Requirements: 1.2 - Mobile user agent string (iPhone 5/SE)
    """
    manager = BrowserManager()
    profile_path = Path("/tmp/test_browser_ua")
    profile_path.mkdir(parents=True, exist_ok=True)
    
    try:
        context = await manager.create_context(
            profile_path=profile_path,
            headless=True
        )
        
        page = await context.new_page()
        
        # Navigate to a simple page to evaluate JavaScript
        await page.goto("about:blank")
        
        # Check user agent
        user_agent = await page.evaluate("navigator.userAgent")
        assert user_agent == USER_AGENT
        assert "iPhone" in user_agent
        assert "Safari" in user_agent
        
        await page.close()
        
    finally:
        await manager.close()
