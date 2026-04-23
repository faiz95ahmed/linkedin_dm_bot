"""CLI entry point for LinkedIn DM Bot.

This module provides command-line interface for the LinkedIn automation bot.
It wires together BrowserManager, NavigationEngine, RateLimiter, and
NotificationService to provide login and navigation commands.

Requirements: 1.1, 2.5, 7.1, 7.2
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from dm_bot.browser import BrowserManager, run_with_headless_fallback
from dm_bot.config import (
    BlockedFlag,
    LI_PASS,
    LI_USER,
    PROFILE_PATH,
    RateLimiter,
    setup_logging,
)
from dm_bot.navigation import NavigationEngine
from dm_bot.notifications import NotificationService
from dm_bot.actions import CheckpointDetectedError
from dm_bot.storage import StorageError

# Initialize Typer app
app = typer.Typer(
    name="dm-bot",
    help="LinkedIn messaging automation bot",
    add_completion=False,
)

# Initialize logger
logger = logging.getLogger(__name__)


class ProgressReporter:
    """
    Displays progress updates during sync operations.
    
    Tracks sync statistics and formats output with clear visual indicators.
    
    Requirements: 3.1, 3.2, 3.3, 3.4
    """
    
    def __init__(self) -> None:
        """Initialize progress reporter with start time and counters."""
        self.start_time = datetime.now()
        self.conversations_processed = 0
        self.messages_stored = 0
        self.messages_skipped = 0
    
    def report_conversation_start(self, index: int, total: int, name: str) -> None:
        """
        Display progress for starting a conversation.
        
        Args:
            index: Current conversation index (1-based)
            total: Total number of conversations to process
            name: Display name of the connection
            
        Requirement 3.1: Display connection name and progress count
        """
        typer.echo(f"Processing {index}/{total}: {name}")
    
    def report_messages_extracted(self, count: int) -> None:
        """
        Display number of messages extracted from a conversation.
        
        Args:
            count: Number of messages found
            
        Requirement 3.2: Display number of messages found
        """
        typer.echo(f"  Found {count} messages")
    
    def report_messages_stored(self, new: int, skipped: int) -> None:
        """
        Display storage results for a conversation.
        
        Args:
            new: Number of new messages stored
            skipped: Number of duplicate messages skipped
            
        Requirement 3.3: Display new vs skipped messages
        """
        self.messages_stored += new
        self.messages_skipped += skipped
        typer.echo(f"  Stored {new} new, skipped {skipped} duplicates")
        self.conversations_processed += 1
    
    def report_error(self, error: str) -> None:
        """
        Display error message for a failed conversation.
        
        Args:
            error: Error message to display
        """
        typer.echo(f"  ✗ Error: {error}", err=True)
    
    def report_final_summary(self, errors: list[str], rate_limit_stats: dict[str, float] | None = None) -> None:
        """
        Display final sync summary with statistics.
        
        Args:
            errors: List of error messages encountered during sync
            rate_limit_stats: Optional rate limiting statistics from RateLimiter
            
        Requirements: 1.3, 3.4, 5.4
        """
        elapsed = datetime.now() - self.start_time
        
        typer.echo("\n" + "=" * 60)
        typer.echo("Sync Complete")
        typer.echo("=" * 60)
        typer.echo(f"Conversations processed: {self.conversations_processed}")
        typer.echo(f"Messages stored: {self.messages_stored}")
        typer.echo(f"Messages skipped (duplicates): {self.messages_skipped}")
        typer.echo(f"Time elapsed: {elapsed}")
        
        # Display rate limiting statistics - Requirement 5.4
        if rate_limit_stats:
            typer.echo(f"\nRate Limiting:")
            typer.echo(f"  Total actions: {int(rate_limit_stats['total_actions'])}")
            typer.echo(f"  Average delay: {rate_limit_stats['average_delay']:.2f}s")
        
        if errors:
            typer.echo(f"\nErrors encountered: {len(errors)}")
            for error in errors[:5]:  # Show first 5 errors
                typer.echo(f"  - {error}")
            if len(errors) > 5:
                typer.echo(f"  ... and {len(errors) - 5} more")


def validate_credentials() -> tuple[str, str]:
    """
    Validate and load credentials from environment variables.
    
    Returns:
        Tuple of (username, password)
        
    Raises:
        typer.Exit: If credentials are not set
        
    Requirement 1.1: Load credentials from environment variables LI_USER and LI_PASS
    """
    if not LI_USER or not LI_PASS:
        typer.echo(
            "Error: Credentials not found in environment variables.",
            err=True,
        )
        typer.echo(
            "Please set LI_USER and LI_PASS in your .env file or environment.",
            err=True,
        )
        raise typer.Exit(code=1)
    
    return LI_USER, LI_PASS


@app.command()
def login(
    profile_path: Optional[Path] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Path to browser profile directory",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run browser in headless mode (not recommended for checkpoints)",
    ),
) -> None:
    """
    Open browser for manual login to LinkedIn.
    
    This command launches a browser with the configured profile and navigates
    to the LinkedIn login page. You can manually complete the login process,
    including any security checkpoints. The session will be saved in the
    browser profile for future automated runs.
    
    Requirement 1.1: Load credentials from environment variables
    """
    # Set up logging
    setup_logging(command="login")

    logger.info("Starting login command")
    
    # Validate credentials
    username, password = validate_credentials()
    
    # Use default profile path if not provided
    if profile_path is None:
        profile_path = PROFILE_PATH
    
    logger.info(f"Using profile path: {profile_path}")
    
    # Run async login flow
    asyncio.run(_login_flow(username, password, profile_path, headless))


async def _login_flow(
    username: str,
    password: str,
    profile_path: Path,
    headless: bool,
) -> None:
    """
    Async implementation of login flow.
    
    Args:
        username: LinkedIn username/email
        password: LinkedIn password
        profile_path: Path to browser profile
        headless: Whether to run in headless mode
    """
    browser_manager = BrowserManager()
    
    try:
        # Create browser context
        context = await browser_manager.create_context(
            profile_path=profile_path,
            headless=headless,
        )
        
        # Create page
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Initialize components
        rate_limiter = RateLimiter()
        notifier = NotificationService()
        nav_engine = NavigationEngine(
            page=page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Attempt login
        logger.info("Attempting to log in to LinkedIn")
        success = await nav_engine.login(username, password)
        
        if success:
            typer.echo("✓ Login successful!")
            logger.info("Login completed successfully")
            
            # Keep browser open for manual verification
            typer.echo("\nBrowser will remain open for manual verification.")
            typer.echo("Press Ctrl+C to close the browser and exit.")
            
            try:
                # Wait indefinitely until user interrupts
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                typer.echo("\nClosing browser...")
                logger.info("User interrupted, closing browser")
        else:
            typer.echo("✗ Login failed. Please check your credentials.", err=True)
            logger.error("Login failed")
            raise typer.Exit(code=1)
            
    except CheckpointDetectedError as e:
        typer.echo(f"✗ Security checkpoint detected: {e}", err=True)
        logger.error(f"Checkpoint detected: {e}")
        typer.echo("\nPlease complete the checkpoint manually in the browser.")
        typer.echo("Press Ctrl+C when done to close the browser.")
        
        try:
            # Wait for user to complete checkpoint
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            typer.echo("\nClosing browser...")
            logger.info("User completed checkpoint, closing browser")
            
    except Exception as e:
        typer.echo(f"✗ Error during login: {type(e).__name__}: {e}", err=True)
        logger.error(f"Login error: {type(e).__name__}: {e}", exc_info=True)
        
        # Send error notification
        notifier = NotificationService()
        notifier.notify_error(e)
        
        # Clean up browser on fatal error (Requirement 5.5)
        await browser_manager.close_on_fatal_error(e)
        raise typer.Exit(code=1)
        
    finally:
        # Always close browser cleanly
        await browser_manager.close()


@app.command()
def navigate(
    profile_path: Optional[Path] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Path to browser profile directory",
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Run browser in headless mode (not recommended for checkpoints)",
    ),
) -> None:
    """
    Test navigation to LinkedIn messaging interface.
    
    This command launches a browser with the configured profile, logs in if
    necessary, and navigates to the messaging interface. This is useful for
    testing the navigation flow and verifying that the bot can successfully
    reach the messaging page.
    
    Requirements:
        - 1.1: Load credentials from environment variables
        - 2.5: Proceed to messaging after successful login
    """
    # Set up logging
    setup_logging(command="navigate")

    logger.info("Starting navigate command")
    
    # Validate credentials
    username, password = validate_credentials()
    
    # Use default profile path if not provided
    if profile_path is None:
        profile_path = PROFILE_PATH
    
    logger.info(f"Using profile path: {profile_path}")
    
    # Run async navigation flow
    asyncio.run(_navigate_flow(username, password, profile_path, headless))


async def _navigate_flow(
    username: str,
    password: str,
    profile_path: Path,
    headless: bool,
) -> None:
    """
    Async implementation of navigation flow.
    
    Args:
        username: LinkedIn username/email
        password: LinkedIn password
        profile_path: Path to browser profile
        headless: Whether to run in headless mode
    """
    browser_manager = BrowserManager()
    
    try:
        # Create browser context
        context = await browser_manager.create_context(
            profile_path=profile_path,
            headless=headless,
        )
        
        # Create page
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Initialize components
        rate_limiter = RateLimiter()
        notifier = NotificationService()
        nav_engine = NavigationEngine(
            page=page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Navigate to LinkedIn home
        logger.info("Navigating to LinkedIn")
        await page.goto("https://www.linkedin.com")
        await rate_limiter.delay_after_page_load()
        
        # Check if login is required
        if await nav_engine.check_for_checkpoint():
            typer.echo("✗ Checkpoint detected. Please run 'login' command first.", err=True)
            logger.error("Checkpoint detected on initial page load")
            raise typer.Exit(code=1)
        
        # Check if we need to login
        url = page.url.lower()
        if "/login" in url:
            logger.info("Login required, attempting to log in")
            typer.echo("Login required, attempting to log in...")
            
            success = await nav_engine.login(username, password)
            if not success:
                typer.echo("✗ Login failed. Please check your credentials.", err=True)
                logger.error("Login failed")
                raise typer.Exit(code=1)
            
            typer.echo("✓ Login successful!")
            logger.info("Login completed successfully")
        else:
            typer.echo("✓ Already logged in")
            logger.info("Already logged in, skipping login flow")
        
        # Navigate to messaging (Requirement 2.5)
        logger.info("Navigating to messaging interface")
        typer.echo("Navigating to messaging...")
        
        success = await nav_engine.navigate_to_messaging()
        
        if success:
            typer.echo("✓ Successfully navigated to messaging interface!")
            logger.info("Navigation to messaging completed successfully")
            
            # Keep browser open for inspection
            typer.echo("\nBrowser will remain open for inspection.")
            typer.echo("Press Ctrl+C to close the browser and exit.")
            
            try:
                # Wait indefinitely until user interrupts
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                typer.echo("\nClosing browser...")
                logger.info("User interrupted, closing browser")
        else:
            typer.echo("✗ Failed to navigate to messaging interface.", err=True)
            logger.error("Navigation to messaging failed")
            raise typer.Exit(code=1)
            
    except CheckpointDetectedError as e:
        typer.echo(f"✗ Security checkpoint detected: {e}", err=True)
        logger.error(f"Checkpoint detected: {e}")
        typer.echo("\nPlease complete the checkpoint manually in the browser.")
        typer.echo("Press Ctrl+C when done to close the browser.")
        
        try:
            # Wait for user to complete checkpoint
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            typer.echo("\nClosing browser...")
            logger.info("User completed checkpoint, closing browser")
            
    except Exception as e:
        typer.echo(f"✗ Error during navigation: {type(e).__name__}: {e}", err=True)
        logger.error(f"Navigation error: {type(e).__name__}: {e}", exc_info=True)
        
        # Send error notification
        notifier = NotificationService()
        notifier.notify_error(e)
        
        # Clean up browser on fatal error (Requirement 5.5)
        await browser_manager.close_on_fatal_error(e)
        raise typer.Exit(code=1)
        
    finally:
        # Always close browser cleanly
        await browser_manager.close()


@app.command()
def sync(
    since: Optional[datetime] = typer.Option(
        None,
        "--since",
        "-s",
        help="Only sync conversations with activity after this date (ISO format: YYYY-MM-DD)",
        formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"],
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Maximum number of conversations to sync",
    ),
    profile_path: Optional[Path] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Path to browser profile directory",
    ),
) -> None:
    """
    Sync conversations and messages from LinkedIn to local database.

    This command navigates to the LinkedIn messaging inbox, extracts
    conversation previews, and syncs messages to the local SQLite database.
    Supports incremental sync with --since and --limit options.

    Requirements:
        - 7.1: Filter by --since date parameter
        - 7.2: Respect --limit parameter
    """
    # Set up logging
    setup_logging(command="sync")

    logger.info("Starting sync command")

    # Validate credentials
    username, password = validate_credentials()

    # Use default profile path if not provided
    if profile_path is None:
        profile_path = PROFILE_PATH

    logger.info(f"Using profile path: {profile_path}")

    if since:
        logger.info(f"Filtering conversations since: {since}")
    logger.info(f"Limit: {limit} conversations")

    # Run async sync flow, headless with automatic non-headless fallback
    asyncio.run(run_with_headless_fallback(_sync_flow, profile_path, username, password, since=since, limit=limit))


async def _sync_flow(
    username: str,
    password: str,
    since: Optional[datetime],
    limit: int,
    profile_path: Path = PROFILE_PATH,
    headless: bool = True,
) -> None:
    """
    Async implementation of sync flow.
    
    Args:
        username: LinkedIn username/email
        password: LinkedIn password
        profile_path: Path to browser profile
        headless: Whether to run in headless mode
        since: Optional datetime to filter conversations
        limit: Maximum number of conversations to sync
        
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 4.2, 4.3, 4.4
    """
    from dm_bot.extraction import SyncEngine
    from dm_bot.storage import DatabaseManager, SyncRepository

    blocked_flag = BlockedFlag()
    browser_manager = BrowserManager()
    db: Optional[DatabaseManager] = None
    progress_reporter: Optional[ProgressReporter] = None
    
    try:
        # Initialize database
        db = DatabaseManager()
        db.initialize_schema()
        typer.echo("✓ Database initialized")
        
        # Create browser context
        context = await browser_manager.create_context(
            profile_path=profile_path,
            headless=headless,
        )
        
        # Create page
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Initialize components
        rate_limiter = RateLimiter()
        notifier = NotificationService()
        nav_engine = NavigationEngine(
            page=page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Navigate to LinkedIn home
        logger.info("Navigating to LinkedIn")
        typer.echo("Navigating to LinkedIn...")
        await page.goto("https://www.linkedin.com")
        await rate_limiter.delay_after_page_load()
        
        # Check if login is required
        url = page.url.lower()
        if "/login" in url:
            logger.info("Login required, attempting to log in")
            typer.echo("Login required, attempting to log in...")
            
            success = await nav_engine.login(username, password)
            if not success:
                typer.echo("✗ Login failed. Please check your credentials.", err=True)
                logger.error("Login failed")
                blocked_flag.set("Login failed: credentials rejected or login flow broken")
                typer.echo("Blocked flag set — next run will skip headless attempt.")
                raise typer.Exit(code=1)

            typer.echo("✓ Login successful!")
            logger.info("Login completed successfully")
        else:
            typer.echo("✓ Already logged in")
            logger.info("Already logged in, skipping login flow")

        # Navigate to messaging
        logger.info("Navigating to messaging interface")
        typer.echo("Navigating to messaging...")
        
        success = await nav_engine.navigate_to_messaging()
        
        if not success:
            typer.echo("✗ Failed to navigate to messaging interface.", err=True)
            logger.error("Navigation to messaging failed")
            raise typer.Exit(code=1)
        
        typer.echo("✓ Reached messaging interface")
        
        # Initialize sync engine
        sync_engine = SyncEngine(
            page=page,
            db=db,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Create progress reporter - Requirement 1.2
        progress_reporter = ProgressReporter()
        
        # Define progress callback - Requirements 3.1, 3.2, 3.3
        def progress_callback(event_type: str, data: dict) -> None:
            """Handle progress events from SyncEngine."""
            if event_type == "conversation_start":
                progress_reporter.report_conversation_start(
                    index=data["index"],
                    total=data["total"],
                    name=data["name"],
                )
            elif event_type == "messages_extracted":
                progress_reporter.report_messages_extracted(count=data["count"])
            elif event_type == "messages_stored":
                progress_reporter.report_messages_stored(
                    new=data["new"],
                    skipped=data["skipped"],
                )
        
        # Run sync with progress callback
        typer.echo(f"\nSyncing conversations (limit: {limit})...")
        if since:
            typer.echo(f"Filtering conversations since: {since.strftime('%Y-%m-%d')}")
        typer.echo("")  # Blank line before progress
        
        result = await sync_engine.sync_conversations(
            since=since,
            limit=limit,
            progress_callback=progress_callback,
        )
        
        # Display final summary using ProgressReporter - Requirement 1.3
        rate_limit_stats = rate_limiter.get_statistics()
        progress_reporter.report_final_summary(errors=result.errors, rate_limit_stats=rate_limit_stats)
        
        logger.info(
            f"Sync complete: {result.conversations_processed} conversations, "
            f"{result.messages_stored} new messages"
        )
        blocked_flag.clear()

        # Record successful sync
        SyncRepository(db).record("linkedin")

    except CheckpointDetectedError as e:
        # Requirement 4.1: Handle checkpoint detection
        typer.echo(f"\n✗ Security checkpoint detected: {e}", err=True)
        logger.error(f"Checkpoint detected: {e}")
        blocked_flag.set(f"Checkpoint detected: {e}")
        typer.echo("Blocked flag set — next run will skip headless attempt.")

        # Display partial results if available
        if progress_reporter:
            typer.echo("\nPartial results before checkpoint:")
            rate_limit_stats = rate_limiter.get_statistics()
            progress_reporter.report_final_summary(errors=[], rate_limit_stats=rate_limit_stats)
        
        # Send notification
        notifier = NotificationService()
        notifier.notify_error(e)
        
        typer.echo("\nPlease complete the checkpoint manually in the browser.")
        typer.echo("Press Ctrl+C when done to close the browser.")
        
        try:
            # Wait for user to complete checkpoint
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            typer.echo("\nClosing browser...")
            logger.info("User completed checkpoint, closing browser")
            
    except KeyboardInterrupt:
        # Requirement 4.4: Handle user interruption gracefully
        typer.echo("\n\n✗ Interrupted by user", err=True)
        logger.info("Sync interrupted by user (Ctrl+C)")
        
        # Display partial results
        if progress_reporter:
            typer.echo("\nPartial results:")
            rate_limit_stats = rate_limiter.get_statistics()
            progress_reporter.report_final_summary(errors=[], rate_limit_stats=rate_limit_stats)
        
        # Exit gracefully with code 0
        
    except Exception as e:
        typer.echo(f"\n✗ Error during sync: {type(e).__name__}: {e}", err=True)
        logger.error(f"Sync error: {type(e).__name__}: {e}", exc_info=True)
        
        # Display partial results if available
        if progress_reporter:
            typer.echo("\nPartial results before error:")
            rate_limit_stats = rate_limiter.get_statistics()
            progress_reporter.report_final_summary(errors=[str(e)], rate_limit_stats=rate_limit_stats)
        
        # Send error notification
        notifier = NotificationService()
        notifier.notify_error(e)
        
        # Clean up browser on fatal error
        await browser_manager.close_on_fatal_error(e)
        raise typer.Exit(code=1)
        
    finally:
        # Always close browser cleanly
        await browser_manager.close()
        
        # Close database connection
        if db is not None:
            db.close()


@app.command()
def sync_conversation(
    url: str = typer.Argument(..., help="LinkedIn conversation URL to sync"),
    profile_path: Optional[Path] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Path to browser profile directory",
    ),
) -> None:
    """
    Sync a specific conversation by URL.

    Navigates directly to the given LinkedIn conversation URL, extracts
    connection info and all messages (with scrolling), and stores them to
    the local SQLite database.  Useful for testing or re-syncing a single
    conversation without going through the inbox.

    Example:
        dm-bot sync-conversation https://www.linkedin.com/messaging/thread/2-xxx/
    """
    setup_logging(command="sync-conversation")
    username, password = validate_credentials()
    if profile_path is None:
        profile_path = PROFILE_PATH
    asyncio.run(run_with_headless_fallback(_sync_conversation_flow, profile_path, username, password, url=url))


async def _sync_conversation_flow(
    username: str,
    password: str,
    url: str,
    profile_path: Path = PROFILE_PATH,
    headless: bool = True,
) -> None:
    """Async implementation of sync-conversation command."""
    from dm_bot.extraction import SyncEngine, ConversationPreview
    from dm_bot.storage import DatabaseManager

    browser_manager = BrowserManager()
    db: Optional[DatabaseManager] = None

    try:
        db = DatabaseManager()
        db.initialize_schema()
        typer.echo("✓ Database initialized")

        context = await browser_manager.create_context(
            profile_path=profile_path,
            headless=headless,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        rate_limiter = RateLimiter()
        notifier = NotificationService()
        nav_engine = NavigationEngine(
            page=page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )

        # Ensure we're logged in
        typer.echo("Navigating to LinkedIn...")
        await page.goto("https://www.linkedin.com")
        await rate_limiter.delay_after_page_load()

        page_url = page.url.lower()
        if "/login" in page_url:
            typer.echo("Login required, attempting to log in...")
            success = await nav_engine.login(username, password)
            if not success:
                typer.echo("✗ Login failed.", err=True)
                raise typer.Exit(code=1)
            typer.echo("✓ Login successful!")
        else:
            typer.echo("✓ Already logged in")

        sync_engine = SyncEngine(
            page=page,
            db=db,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )

        # Build a preview; sync_single_conversation handles the navigation.
        typer.echo(f"Navigating to conversation: {url}")
        preview = ConversationPreview(connection_name="", thread_url=url)
        stored, skipped, extracted = await sync_engine.sync_single_conversation(preview)

        typer.echo(f"\n✓ Done: {extracted} messages found, {stored} stored, {skipped} skipped")

    except CheckpointDetectedError as e:
        typer.echo(f"✗ Security checkpoint detected: {e}", err=True)
        typer.echo("Please complete the checkpoint manually in the browser.")
        raise typer.Exit(code=1)

    except Exception as e:
        typer.echo(f"✗ Error: {type(e).__name__}: {e}", err=True)
        logger.error(f"sync-conversation error: {e}", exc_info=True)
        raise typer.Exit(code=1)

    finally:
        await browser_manager.close()
        if db is not None:
            db.close()


@app.command()
def send_message(
    conversation_id: int = typer.Argument(..., help="Conversation ID (from 'dm-bot dump')"),
    message: str = typer.Argument(..., help="Message text to send"),
    attachment: Optional[Path] = typer.Option(
        None,
        "--attachment",
        "-a",
        help="Path to a file to attach to the message",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    profile_path: Optional[Path] = typer.Option(
        None,
        "--profile",
        "-p",
        help="Path to browser profile directory",
    ),
) -> None:
    """Send a message to an existing conversation, then auto-sync."""
    setup_logging(command="send-message")
    username, password = validate_credentials()
    if profile_path is None:
        profile_path = PROFILE_PATH
    asyncio.run(
        run_with_headless_fallback(
            _send_message_flow, profile_path,
            username, password,
            conversation_id=conversation_id, message=message, attachment=attachment,
        )
    )


async def _send_message_flow(
    username: str,
    password: str,
    conversation_id: int,
    message: str,
    attachment: Optional[Path] = None,
    profile_path: Path = PROFILE_PATH,
    headless: bool = True,
) -> None:
    """Async implementation of send-message command."""
    from dm_bot.extraction import SyncEngine, ConversationPreview
    from dm_bot.storage import DatabaseManager, ConversationRepository

    browser_manager = BrowserManager()
    db: Optional[DatabaseManager] = None

    try:
        # 1. Look up conversation from DB
        db = DatabaseManager()
        db.initialize_schema()
        conv_repo = ConversationRepository(db)
        conv = conv_repo.get_by_id(conversation_id)
        if conv is None:
            typer.echo(f"✗ No conversation found with ID {conversation_id}", err=True)
            raise typer.Exit(code=1)
        if not conv.thread_url:
            typer.echo("✗ Conversation has no thread URL. Run sync first.", err=True)
            raise typer.Exit(code=1)

        # 2. Start browser and login
        context = await browser_manager.create_context(
            profile_path=profile_path,
            headless=headless,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        rate_limiter = RateLimiter()
        notifier = NotificationService()
        nav_engine = NavigationEngine(
            page=page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )

        typer.echo("Navigating to LinkedIn...")
        await page.goto("https://www.linkedin.com")
        await rate_limiter.delay_after_page_load()

        page_url = page.url.lower()
        if "/login" in page_url:
            typer.echo("Login required, attempting to log in...")
            success = await nav_engine.login(username, password)
            if not success:
                typer.echo("✗ Login failed.", err=True)
                raise typer.Exit(code=1)
            typer.echo("✓ Login successful!")
        else:
            typer.echo("✓ Already logged in")

        # 3. Send message
        sync_engine = SyncEngine(page=page, db=db, rate_limiter=rate_limiter, notifier=notifier)
        typer.echo(f"Sending message to conversation {conversation_id}...")
        await sync_engine.send_message(
            conv.thread_url,
            message,
            attachment_path=str(attachment) if attachment is not None else None,
        )
        typer.echo("✓ Message sent")
        await asyncio.sleep(3)  # Wait for LinkedIn to reflect the sent message in DOM

        # 4. Auto-sync to confirm stored
        typer.echo("Syncing conversation...")
        preview = ConversationPreview(connection_name="", thread_url=conv.thread_url)
        stored, skipped, extracted = await sync_engine.sync_single_conversation(preview)
        typer.echo(f"✓ Synced: {extracted} messages found, {stored} stored, {skipped} skipped")

    except CheckpointDetectedError as e:
        typer.echo(f"✗ Security checkpoint: {e}", err=True)
        raise typer.Exit(code=1)

    except Exception as e:
        typer.echo(f"✗ Error: {type(e).__name__}: {e}", err=True)
        logger.error(f"send-message error: {e}", exc_info=True)
        raise typer.Exit(code=1)

    finally:
        await browser_manager.close()
        if db is not None:
            db.close()


@app.command()
def dump(
    conversation: Optional[str] = typer.Option(
        None,
        "--conversation",
        "-c",
        help="Filter messages by connection slug",
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        "-l",
        help="Maximum number of messages to display",
    ),
) -> None:
    """
    Dump stored messages for debugging and verification.
    
    Shows: sender, recipient, date, ID, first 100 chars of content.
    
    Use this command to verify sync idempotency and debug issues.
    
    Requirements:
        - 6.1: Display all stored messages with required fields
        - 6.2: Filter by --conversation flag
        - 6.3: Limit number of messages with --limit flag
        - 6.4: Format output in readable table format
        - 6.5: Display informative message when database is empty
    """
    # Set up logging
    setup_logging(command="dump")

    logger.info("Starting dump command")
    
    if conversation:
        logger.info(f"Filtering by conversation: {conversation}")
    logger.info(f"Limit: {limit} messages")
    
    # Run dump
    _dump_messages(conversation, limit)


def _dump_messages(
    conversation_filter: Optional[str],
    limit: int,
    db_override: Optional["DatabaseManager"] = None,
) -> None:
    """
    Implementation of dump command.
    
    Args:
        conversation_filter: Optional connection slug to filter by
        limit: Maximum number of messages to display
        db_override: Optional DatabaseManager for testing (uses default if None)
    """
    from dm_bot.storage import (
        DatabaseManager,
        ConnectionRepository,
        ConversationRepository,
        MessageRepository,
        StorageError,
        Connection,
        Conversation,
    )
    
    db: Optional[DatabaseManager] = None
    should_close_db = False
    
    try:
        # Initialize database
        if db_override is not None:
            db = db_override
        else:
            db = DatabaseManager()
            should_close_db = True
        
        # Check if database exists and has schema
        try:
            db.connect()
        except StorageError:
            typer.echo("No database found. Run 'dm-bot sync' first to create the database.", err=True)
            raise typer.Exit(code=1)
        
        # Initialize repositories
        conn_repo = ConnectionRepository(db)
        conv_repo = ConversationRepository(db)
        msg_repo = MessageRepository(db)
        
        # Get all connections for lookup
        connections = conn_repo.list_all()
        connection_map = {c.id: c for c in connections if c.id is not None}
        slug_to_connection = {c.linkedin_slug: c for c in connections}
        
        # Filter by conversation if specified - Requirement 6.2
        if conversation_filter:
            target_connection = slug_to_connection.get(conversation_filter)
            if target_connection is None:
                typer.echo(f"No connection found with slug: {conversation_filter}", err=True)
                typer.echo("\nAvailable connections:")
                for c in connections[:10]:
                    typer.echo(f"  - {c.linkedin_slug} ({c.display_name})")
                if len(connections) > 10:
                    typer.echo(f"  ... and {len(connections) - 10} more")
                raise typer.Exit(code=1)
            
            if target_connection.id is None:
                typer.echo(f"Connection has no ID: {conversation_filter}", err=True)
                raise typer.Exit(code=1)
            
            # Get conversation for this connection
            target_conv = conv_repo.get_by_connection_id(target_connection.id)
            if target_conv is None:
                typer.echo(f"No conversation found for connection: {conversation_filter}", err=True)
                raise typer.Exit(code=1)
            
            if target_conv.id is None:
                typer.echo(f"Conversation has no ID for connection: {conversation_filter}", err=True)
                raise typer.Exit(code=1)
            
            # Get messages for this conversation
            messages = msg_repo.get_by_conversation(target_conv.id)
            conversation_ids: dict[int, "Conversation"] = {target_conv.id: target_conv}
        else:
            # Get all messages from all conversations
            messages = []
            conversation_ids = {}
            
            for connection in connections:
                if connection.id is None:
                    continue
                conv = conv_repo.get_by_connection_id(connection.id)
                if conv and conv.id is not None:
                    conversation_ids[conv.id] = conv
                    conv_messages = msg_repo.get_by_conversation(conv.id)
                    messages.extend(conv_messages)
        
        # Check if database is empty - Requirement 6.5
        if not messages:
            if conversation_filter:
                typer.echo(f"No messages found for conversation: {conversation_filter}")
            else:
                typer.echo("No messages found in database. Run 'dm-bot sync' to sync messages from LinkedIn.")
            return
        
        # Sort messages by timestamp descending (most recent first)
        messages.sort(key=lambda m: m.timestamp, reverse=True)
        
        # Apply limit - Requirement 6.3
        messages = messages[:limit]
        
        # Build conversation to connection mapping
        conv_to_connection: dict[int, Connection] = {}
        for conv_id, conv in conversation_ids.items():
            if conv.connection_id in connection_map:
                conv_to_connection[conv_id] = connection_map[conv.connection_id]
        
        # Display header - Requirement 6.4
        typer.echo("")
        typer.echo("=" * 100)
        typer.echo(f"{'ID':<8} {'Date':<20} {'Sender':<20} {'Recipient':<20} {'Content':<30}")
        typer.echo("=" * 100)
        
        # Display messages - Requirement 6.1
        for msg in messages:
            # Determine sender and recipient based on direction
            connection_opt = conv_to_connection.get(msg.conversation_id)
            connection_name = connection_opt.display_name if connection_opt else "Unknown"
            
            if msg.direction == "inbound":
                sender = connection_name[:18] + ".." if len(connection_name) > 20 else connection_name
                recipient = "Me"
            else:
                sender = "Me"
                recipient = connection_name[:18] + ".." if len(connection_name) > 20 else connection_name
            
            # Format date
            date_str = msg.timestamp.strftime("%Y-%m-%d %H:%M")
            
            # Truncate content to 100 chars - Requirement 6.1
            content = msg.content.replace("\n", " ").replace("\r", "")
            if len(content) > 28:
                content = content[:25] + "..."
            
            # Format ID
            msg_id = str(msg.id) if msg.id else "N/A"
            
            typer.echo(f"{msg_id:<8} {date_str:<20} {sender:<20} {recipient:<20} {content:<30}")
        
        typer.echo("=" * 100)
        typer.echo(f"Total: {len(messages)} messages displayed")
        
        if len(messages) == limit:
            typer.echo(f"(Limited to {limit} messages. Use --limit to show more.)")
        
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error reading database: {type(e).__name__}: {e}", err=True)
        logger.error(f"Dump error: {type(e).__name__}: {e}", exc_info=True)
        raise typer.Exit(code=1)
    finally:
        if db is not None and should_close_db:
            db.close()


@app.command()
def dump_tree(
    url: Optional[str] = typer.Option(
        "https://www.linkedin.com",
        "--url",
        "-u",
        help="URL to navigate to before dumping",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for dump files",
    ),
    prefix: str = typer.Option(
        "snapshot",
        "--prefix",
        "-p",
        help="Filename prefix for the dump",
    ),
    profile_path: Optional[Path] = typer.Option(
        None,
        "--profile",
        help="Path to browser profile directory",
    ),
) -> None:
    """
    Dump the accessibility tree of a LinkedIn page to JSON.
    
    This command is useful for investigating page structure and designing
    accurate navigation patterns. The output JSON file contains the complete
    accessibility tree with all roles, names, and hierarchy.
    
    Examples:
        dm-bot dump-tree                                    # Dump LinkedIn home
        dm-bot dump-tree --url https://linkedin.com/login   # Dump login page
        dm-bot dump-tree --prefix login_page                # Custom filename
        dm-bot dump-tree --output ./debug_dumps             # Custom directory
    
    Requirements:
        - 2.1: Launch browser and navigate to URL
        - 2.2: Capture and save accessibility tree
        - 2.3: Display file path and exit
        - 2.4: Support --url flag
        - 2.5: Support --output flag
    """
    setup_logging(command="dump-tree")
    logger.info(f"Starting dump-tree command for URL: {url}")
    
    # Use default URL if not provided
    target_url = url if url is not None else "https://www.linkedin.com"
    
    asyncio.run(_dump_tree_flow(target_url, output, prefix, profile_path))


async def _dump_tree_flow(
    url: str,
    output_dir: Optional[Path],
    prefix: str,
    profile_path: Optional[Path],
) -> None:
    """
    Async implementation of dump-tree command.
    
    Args:
        url: URL to navigate to
        output_dir: Output directory for dumps
        prefix: Filename prefix
        profile_path: Browser profile path
        
    Requirements: 2.1, 2.2, 2.3
    """
    from dm_bot.utils import AccessibilityDumper
    
    browser_manager = BrowserManager()
    
    try:
        # Use default profile path if not provided
        if profile_path is None:
            profile_path = PROFILE_PATH
        
        # Create browser context
        typer.echo(f"Launching browser...")
        context = await browser_manager.create_context(
            profile_path=profile_path,
            headless=False,
        )
        
        # Create page
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Navigate to URL (Requirement 2.1)
        typer.echo(f"Navigating to: {url}")
        await page.goto(url)
        await asyncio.sleep(2)  # Wait for page to settle
        
        # Dump accessibility tree (Requirement 2.2)
        dumper = AccessibilityDumper(output_dir=output_dir)
        filepath = await dumper.dump_tree(page, prefix=prefix)
        
        # Display success message (Requirement 2.3)
        typer.echo(f"\n✓ Accessibility tree dumped successfully!")
        typer.echo(f"File: {filepath}")
        typer.echo(f"\nYou can now inspect the JSON file to find element patterns.")
        
    except StorageError as e:
        typer.echo(f"✗ Error dumping tree: {e}", err=True)
        logger.error(f"Dump error: {e}", exc_info=True)
        raise typer.Exit(code=1)
        
    except Exception as e:
        typer.echo(f"✗ Unexpected error: {type(e).__name__}: {e}", err=True)
        logger.error(f"Dump error: {type(e).__name__}: {e}", exc_info=True)
        raise typer.Exit(code=1)
        
    finally:
        # Close browser
        await browser_manager.close()


@app.command()
def inbox(
    limit: int = typer.Option(50, "--limit", "-l", help="Max conversations to show"),
    since: Optional[int] = typer.Option(
        None, "--since", "-s", help="Only show conversations with activity in last N days"
    ),
) -> None:
    """List all conversations with last message summary."""
    setup_logging(command="inbox")
    from dm_bot.storage import DatabaseManager

    db = DatabaseManager()
    db.initialize_schema()
    try:
        conn = db.connect()
        query = """
            SELECT
                c.id,
                cn.display_name,
                c.last_message_at,
                m.content,
                m.direction
            FROM conversation c
            JOIN connection cn ON c.connection_id = cn.id
            LEFT JOIN message m ON m.id = (
                SELECT id FROM message
                WHERE conversation_id = c.id
                ORDER BY timestamp DESC LIMIT 1
            )
        """
        params: list = []
        if since is not None:
            query += " WHERE c.last_message_at >= datetime('now', ?)"
            params.append(f"-{since} days")
        query += " ORDER BY c.last_message_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        if not rows:
            typer.echo("No conversations found.")
            return

        typer.echo(f"{'ID':<6} {'Name':<30} {'Last activity':<20} {'':2} {'Snippet'}")
        typer.echo("─" * 100)
        for row in rows:
            conv_id, name, last_at, content, direction = row
            name_str = (name or "").split("\n")[0].strip()[:28]
            date_str = str(last_at or "")[:16]
            arrow = "→" if direction == "outbound" else "←"
            snippet = (content or "").replace("\n", " ").strip()[:50]
            typer.echo(f"{conv_id:<6} {name_str:<30} {date_str:<20} {arrow}  {snippet}")
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


@app.command()
def conversation(
    conversation_id: int = typer.Argument(..., help="Conversation ID"),
) -> None:
    """Print the full message thread for a conversation."""
    setup_logging(command="conversation")
    from dm_bot.storage import DatabaseManager, ConversationRepository, MessageRepository

    db = DatabaseManager()
    db.initialize_schema()
    try:
        conv_repo = ConversationRepository(db)
        msg_repo = MessageRepository(db)

        conv = conv_repo.get_by_id(conversation_id)
        if conv is None:
            typer.echo(f"✗ No conversation with ID {conversation_id}", err=True)
            raise typer.Exit(code=1)

        # Get contact name
        row = db.connect().execute(
            "SELECT display_name FROM connection WHERE id = ?", (conv.connection_id,)
        ).fetchone()
        name = row[0].split("\n")[0].strip() if row else "Unknown"

        typer.echo(f"Conversation {conversation_id} — {name}")
        typer.echo(f"URL: {conv.thread_url}")
        typer.echo("─" * 80)

        messages = msg_repo.get_by_conversation(conversation_id)
        if not messages:
            typer.echo("(no messages)")
            return

        for msg in messages:
            ts = str(msg.timestamp)[:16]
            arrow = "→ You" if msg.direction == "outbound" else f"← {name}"
            typer.echo(f"\n[{ts}] {arrow}")
            typer.echo(msg.content)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


@app.command()
def get_url(
    conversation_id: int = typer.Argument(..., help="Conversation ID"),
) -> None:
    """Print the thread URL for a conversation."""
    setup_logging(command="get-url")
    from dm_bot.storage import DatabaseManager, ConversationRepository

    db = DatabaseManager()
    db.initialize_schema()
    try:
        conv = ConversationRepository(db).get_by_id(conversation_id)
        if conv is None:
            typer.echo(f"✗ No conversation with ID {conversation_id}", err=True)
            raise typer.Exit(code=1)
        typer.echo(conv.thread_url)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


@app.command()
def find(
    name: str = typer.Argument(..., help="Name to search for (case-insensitive)"),
) -> None:
    """Find conversations by contact name."""
    setup_logging(command="find")
    from dm_bot.storage import DatabaseManager

    db = DatabaseManager()
    db.initialize_schema()
    try:
        rows = db.connect().execute(
            """
            SELECT c.id, cn.display_name, c.last_message_at
            FROM conversation c
            JOIN connection cn ON c.connection_id = cn.id
            WHERE cn.display_name LIKE ?
            ORDER BY c.last_message_at DESC
            """,
            (f"%{name}%",),
        ).fetchall()

        if not rows:
            typer.echo(f"No conversations matching '{name}'.")
            return

        typer.echo(f"{'ID':<6} {'Name':<40} {'Last activity'}")
        typer.echo("─" * 70)
        for conv_id, display_name, last_at in rows:
            name_str = display_name.split("\n")[0].strip()[:38]
            date_str = str(last_at or "")[:16]
            typer.echo(f"{conv_id:<6} {name_str:<40} {date_str}")
    except Exception as e:
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


@app.command()
def logs(
    limit: int = typer.Option(50, "--limit", "-l", help="Max log entries to show"),
    level: Optional[str] = typer.Option(None, "--level", help="Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"),
    module: Optional[str] = typer.Option(None, "--module", help="Filter by module name"),
    command: Optional[str] = typer.Option(None, "--command", help="Filter by CLI command name"),
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Filter by run ID"),
    since: Optional[datetime] = typer.Option(None, "--since", help="Show logs after this datetime", formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]),
    until: Optional[datetime] = typer.Option(None, "--until", help="Show logs before this datetime", formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]),
    errors_only: bool = typer.Option(False, "--errors-only", "-e", help="Show only ERROR and CRITICAL entries"),
    runs: bool = typer.Option(False, "--runs", help="List recent runs instead of individual log entries"),
) -> None:
    """Query the structured log table."""
    from dm_bot.storage import DatabaseManager

    db = DatabaseManager()
    try:
        conn = db.connect()

        if runs:
            # Show a summary of recent runs
            query = """
                SELECT run_id, command, MIN(ts) AS started, MAX(ts) AS ended,
                       COUNT(*) AS entries,
                       SUM(CASE WHEN level_no >= 40 THEN 1 ELSE 0 END) AS errors
                FROM log
            """
            conditions: list[str] = []
            params: list = []
            if command:
                conditions.append("command = ?")
                params.append(command)
            if since:
                conditions.append("ts >= ?")
                params.append(since.strftime("%Y-%m-%d %H:%M:%S"))
            if until:
                conditions.append("ts <= ?")
                params.append(until.strftime("%Y-%m-%d %H:%M:%S"))
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " GROUP BY run_id ORDER BY started DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()
            if not rows:
                typer.echo("No runs found.")
                return

            typer.echo(f"{'Run ID':<38} {'Command':<20} {'Started':<22} {'Ended':<22} {'Entries':>8} {'Errors':>8}")
            typer.echo("─" * 120)
            for row in rows:
                rid, cmd, started, ended, entries, errors_count = row
                typer.echo(f"{rid:<38} {cmd:<20} {str(started):<22} {str(ended):<22} {entries:>8} {errors_count:>8}")
            return

        # Show individual log entries
        query = "SELECT ts, level, logger, module, func, lineno, message, exc_text, run_id, command FROM log"
        conditions = []
        params = []

        if level:
            conditions.append("level = ?")
            params.append(level.upper())
        if errors_only:
            conditions.append("level_no >= 40")
        if module:
            conditions.append("module = ?")
            params.append(module)
        if command:
            conditions.append("command = ?")
            params.append(command)
        if run_id:
            conditions.append("run_id = ?")
            params.append(run_id)
        if since:
            conditions.append("ts >= ?")
            params.append(since.strftime("%Y-%m-%d %H:%M:%S"))
        if until:
            conditions.append("ts <= ?")
            params.append(until.strftime("%Y-%m-%d %H:%M:%S"))

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        if not rows:
            typer.echo("No log entries found.")
            return

        for row in reversed(rows):
            ts, lvl, lgr, mod, func, lineno, message, exc_text, rid, cmd = row
            header = f"[{ts}] {lvl:<8} {mod}:{func}:{lineno}  (cmd={cmd})"
            typer.echo(header)
            typer.echo(f"  {message}")
            if exc_text:
                for line in exc_text.strip().split("\n"):
                    typer.echo(f"  {line}")
            typer.echo("")

        typer.echo(f"({len(rows)} entries shown)")

    except Exception as e:
        typer.echo(f"✗ Error querying logs: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        db.close()


def main() -> None:
    """Main entry point for the CLI application."""
    app()


if __name__ == "__main__":
    main()
