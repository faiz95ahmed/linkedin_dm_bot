"""Browser management module for Playwright automation."""

import logging
from pathlib import Path
from typing import Callable, Optional

import typer

from playwright.async_api import (
    Browser,
    BrowserContext,
    Playwright,
    async_playwright,
)

from dm_bot.config import (
    BlockedFlag,
    HEADLESS,
    PROFILE_PATH,
    USER_AGENT,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
)

logger = logging.getLogger(__name__)

# Errors that indicate the headless browser couldn't make progress
_NAVIGATION_ERROR_TYPES = (
    "ElementNotFoundError",
    "NavigationTimeoutError",
    "ExtractionError",
    "TimeoutError",
    "CheckpointDetectedError",
)


async def run_with_headless_fallback(
    flow_fn,
    profile_path: Path,
    *args,
    **kwargs,
) -> None:
    """Run an async flow headless, falling back to non-headless on navigation failures.

    The flow function must accept ``headless: bool`` and ``profile_path: Path``
    as keyword arguments.  On the first attempt it runs headless=True.  If a
    navigation-related error is raised the browser is closed, re-opened
    non-headless, and the flow is retried once.  On the second failure the
    error is logged and execution stops (no exception is re-raised).

    If the blocked flag is set (from a previous failed run), the headless
    attempt is skipped entirely and the flow goes straight to non-headless.

    Args:
        flow_fn: Async function implementing the browser flow.
        profile_path: Browser profile path forwarded to the flow.
        *args: Positional arguments forwarded to flow_fn.
        **kwargs: Keyword arguments forwarded to flow_fn (must NOT include
                  ``headless`` or ``profile_path`` — those are managed here).
    """
    flag = BlockedFlag()

    if flag.is_set():
        reason = flag.reason() or "unknown"
        logger.warning(f"Blocked flag is set ({reason}), skipping headless attempt")
        typer.echo(f"⚠ Blocked flag set ({reason}). Starting non-headless directly.")
        attempts = [(1, False)]
    else:
        attempts = [(0, True), (1, False)]

    for attempt, headless in attempts:
        try:
            await flow_fn(*args, profile_path=profile_path, headless=headless, **kwargs)
            return
        except Exception as e:
            error_name = type(e).__name__
            if attempt == 0 and (
                error_name in _NAVIGATION_ERROR_TYPES
                or isinstance(e, (TimeoutError, OSError))
            ):
                logger.warning(
                    f"Headless flow failed with {error_name}: {e}. "
                    "Retrying non-headless..."
                )
                typer.echo(
                    f"⚠ Headless browser couldn't complete the flow ({error_name}). "
                    "Relaunching with visible browser...",
                )
            elif attempt == 1:
                # Non-headless attempt also failed — stop, don't propagate
                logger.error(
                    f"Non-headless retry also failed with {error_name}: {e}",
                    exc_info=True,
                )
                typer.echo(
                    f"✗ Flow could not complete even with visible browser "
                    f"({error_name}: {e}). Stopping.",
                    err=True,
                )
                flag.set(f"Non-headless failed: {error_name}: {e}")
                typer.echo("Blocked flag set — next run will skip headless attempt.")
                return
            else:
                # Non-navigation error on first attempt — re-raise immediately
                raise


class BrowserManager:
    """Manages Playwright browser lifecycle and configuration."""

    def __init__(self):
        """Initialize browser manager."""
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    async def create_context(
        self,
        profile_path: Optional[Path] = None,
        headless: bool = HEADLESS,
    ) -> BrowserContext:
        """
        Create a persistent browser context with mobile viewport.

        Configures the browser with:
        - Mobile viewport (320×568 - iPhone 5/SE)
        - iPhone user agent string
        - Persistent profile for session storage

        Args:
            profile_path: Path to persistent profile directory.
                         Defaults to PROFILE_PATH from config.
            headless: Whether to run in headless mode.
                     Must be False for manual checkpoint resolution.

        Returns:
            Configured BrowserContext with mobile viewport and user agent.

        Requirements:
            - 1.2: Mobile user agent string
            - 1.3: Mobile viewport (320×568)
        """
        if profile_path is None:
            profile_path = PROFILE_PATH

        # Ensure profile directory exists
        profile_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Starting browser with profile: {profile_path}, "
            f"headless: {headless}"
        )
        logger.info(
            f"Viewport: {VIEWPORT_WIDTH}×{VIEWPORT_HEIGHT}, "
            f"User-Agent: {USER_AGENT}"
        )

        # Launch Playwright
        self.playwright = await async_playwright().start()

        # Launch browser with persistent context
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=headless,
            viewport={
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT,
            },
            user_agent=USER_AGENT,
        )

        logger.info("Browser context created successfully")
        return self.context

    async def close(self) -> None:
        """
        Close browser context and clean up resources.

        Ensures graceful shutdown of the browser and Playwright instance.
        This method is safe to call multiple times and handles errors gracefully.
        
        Requirement 5.5: Clean browser context closure on fatal errors
        """
        logger.info("Closing browser context")

        try:
            if self.context:
                await self.context.close()
                self.context = None
                logger.info("Browser context closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser context: {e}")

        try:
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
                logger.info("Playwright stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping Playwright: {e}")
    
    async def close_on_fatal_error(self, error: Exception) -> None:
        """
        Close browser cleanly on fatal errors.
        
        This method ensures the browser context is properly closed even when
        a fatal error occurs, preventing resource leaks.
        
        Args:
            error: The fatal error that triggered the closure
            
        Requirement 5.5: Clean browser context closure on fatal errors
        """
        logger.error(f"Fatal error occurred: {type(error).__name__}: {error}")
        logger.info("Initiating clean browser closure due to fatal error")
        
        try:
            await self.close()
            logger.info("Browser closed cleanly after fatal error")
        except Exception as e:
            logger.error(f"Error during fatal error cleanup: {e}")
            # Continue anyway - we're already in an error state
