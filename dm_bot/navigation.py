"""Navigation engine for LinkedIn automation.

This module orchestrates navigation flows, executes action sequences,
and detects abnormal states like security checkpoints.

Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5
"""

import logging
import re
from typing import Any, Optional

from playwright.async_api import Page

from dm_bot.actions import (
    Action,
    ActionExecutor,
    CheckpointDetectedError,
    ConditionalAction,
)
from dm_bot.config import CHECKPOINT_PATTERNS, RateLimiter
from dm_bot.notifications import NotificationService

logger = logging.getLogger(__name__)


async def has_cookie_dialog(page: Page) -> bool:
    """
    Check if page has a cookie consent dialog.
    
    Based on actual LinkedIn accessibility dumps (linkedin_home_20260201_131305.json),
    the cookie dialog contains buttons with exact names "Accept" and "Reject".
    The dialog appears with heading "LinkedIn respects your privacy" and text
    "Select Accept to consent or Reject to decline non-".
    
    Args:
        page: Playwright page to check
        
    Returns:
        True if cookie dialog is present, False otherwise
        
    Requirements:
        - 4.1: Detect cookie consent dialog by checking for cookie-related buttons
    """
    # Based on actual dumps, the cookie dialog has simple button names
    # Pattern refined in task 11.1
    patterns = [
        r"^Accept$",  # Exact match for "Accept" button
        r"^Reject$",  # Exact match for "Reject" button
    ]
    
    for pattern in patterns:
        try:
            element = page.get_by_role(
                "button", 
                name=re.compile(pattern, re.I)
            )
            count = await element.count()
            if count > 0:
                logger.debug(f"Cookie dialog detected with pattern: {pattern}")
                return True
        except Exception as e:
            logger.debug(f"Pattern check failed: {pattern}, error: {e}")
            continue
    
    return False


async def has_signin_selection(page: Page) -> bool:
    """
    Check if page shows sign-in method selection.
    
    Based on actual LinkedIn accessibility dumps and actions.md:
    The sign-in selection page contains a link "Sign in with email"
    
    Args:
        page: Playwright page to check
        
    Returns:
        True if sign-in selection page is present, False otherwise
        
    Requirements:
        - 5.1: Detect sign-in method selection page by checking for "Sign in with email" link
    """
    try:
        # Try to find "Sign in with email" link
        element = page.get_by_role(
            "link", 
            name=re.compile(r"Sign in with email", re.I)
        )
        count = await element.count()
        if count > 0:
            logger.debug("Sign-in selection page detected")
            return True
    except Exception as e:
        logger.debug(f"Sign-in selection check failed: {e}")
    
    return False


async def has_login_form(page: Page) -> bool:
    """
    Check if page shows email/password login form.
    
    Based on actual LinkedIn accessibility dumps and actions.md:
    The login form contains input fields with aria-labels "Email or phone" and "Password"
    
    Args:
        page: Playwright page to check
        
    Returns:
        True if login form is present, False otherwise
        
    Requirements:
        - 8.3: Detect login form by checking for email/password form fields
    """
    try:
        # Check for email field
        email_field = page.get_by_role(
            "textbox", 
            name=re.compile(r"Email or phone", re.I)
        )
        email_count = await email_field.count()
        
        if email_count > 0:
            logger.debug("Login form detected")
            return True
    except Exception as e:
        logger.debug(f"Login form check failed: {e}")
    
    return False


class NavigationEngine:
    """Orchestrates navigation flows and checkpoint detection."""

    def __init__(
        self,
        page: Page,
        rate_limiter: RateLimiter,
        notifier: NotificationService,
        conditional_actions: Optional[list["ConditionalAction"]] = None,
    ):
        """
        Initialize navigation engine.

        Args:
            page: Playwright page object
            rate_limiter: Rate limiter for human-like delays
            notifier: Notification service for alerts
            conditional_actions: Optional list of conditional actions to check before main flows
        
        Requirements:
            - 7.4: Sort conditional actions by priority automatically
        """
        self.page = page
        self.rate_limiter = rate_limiter
        self.notifier = notifier
        self.executor = ActionExecutor(page=page, rate_limiter=rate_limiter)
        
        # Sort conditional actions by priority (highest first) - Requirement 7.4
        self.conditional_actions = sorted(
            conditional_actions or [],
            key=lambda a: a.priority,
            reverse=True,
        )
        
        logger.debug(
            f"NavigationEngine initialized with {len(self.conditional_actions)} conditional actions"
        )

    async def check_for_checkpoint(self) -> bool:
        """
        Check if current page is a checkpoint or login wall.

        Detects LinkedIn security verification pages and authentication
        barriers by checking URL patterns.

        Returns:
            True if checkpoint detected, False otherwise

        Requirements:
            - 2.2: Detect /checkpoint/ URLs
            - 2.3: Detect /authwall URLs
            - 2.4: Stop automation and notify user when checkpoint detected
        """
        url = self.page.url.lower()

        for pattern in CHECKPOINT_PATTERNS:
            if pattern in url:
                logger.error(
                    f"Checkpoint detected: URL contains '{pattern}' - {url}"
                )
                return True

        return False

    async def execute_flow(
        self,
        actions: list[Action],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Execute a sequence of actions.

        Runs through a list of actions in order, applying rate limiting
        and checking for checkpoints after each navigation action.

        Args:
            actions: List of Action objects to execute
            context: Shared context dictionary for passing data between actions

        Returns:
            Updated context with results from actions

        Raises:
            CheckpointDetectedError: When LinkedIn security checkpoint is encountered
            NavigationTimeoutError: When navigation exceeds timeout

        Requirements:
            - 3.2: Click messaging link to navigate
            - 3.3: Wait for conversation list to load
            - 3.5: Retry navigation on timeout
        """
        if context is None:
            context = {}

        logger.info(f"Executing flow with {len(actions)} actions")

        for i, action in enumerate(actions):
            logger.info(
                f"Executing action {i + 1}/{len(actions)}: {action.name}"
            )

            # Check rate limit before action
            await self.rate_limiter.check_rate_limit()

            # Execute action
            success, context = await self.executor.execute(action, context)

            if not success:
                logger.warning(
                    f"Action failed: {action.name}, continuing with flow"
                )
                # Continue with flow even if action fails
                # The executor has already handled retries

            # Check for checkpoint after each action
            if await self.check_for_checkpoint():
                logger.error("Checkpoint detected during flow execution")
                self.notifier.notify_checkpoint(self.page.url)
                raise CheckpointDetectedError(
                    f"Checkpoint detected at: {self.page.url}"
                )

            # Apply delay after page load if this was a navigation action
            if action.action_type == "click":
                await self.rate_limiter.delay_after_page_load()

        logger.info("Flow execution completed successfully")
        return context

    async def execute_with_conditionals(
        self,
        main_actions: list[Action],
        max_conditional_checks: int = 5,
    ) -> bool:
        """
        Execute actions with conditional pre-checks.
        
        Before executing main actions, checks all conditional actions in
        priority order. If a condition matches, executes that action and
        re-evaluates from the beginning. Continues until no conditions match
        or max checks reached.
        
        Args:
            main_actions: The main action flow to execute
            max_conditional_checks: Maximum number of conditional check cycles (default: 5)
            
        Returns:
            True if flow completed successfully
            
        Requirements:
            - 6.1: Check conditional actions in priority order
            - 6.2: Execute matching action and stop checking lower-priority
            - 6.3: Re-evaluate after page state change
            - 6.4: Proceed with main flow when no conditions match
            - 6.5: Prevent infinite loops with max iterations
        """
        checks_performed = 0
        
        logger.info(
            f"Starting conditional action checks (max: {max_conditional_checks})"
        )
        
        # Check conditional actions in priority order (Requirement 6.1)
        while checks_performed < max_conditional_checks:
            action_executed = False
            
            for conditional_action in self.conditional_actions:
                logger.debug(
                    f"Checking condition: {conditional_action.name} "
                    f"(priority: {conditional_action.priority})"
                )
                
                # Check if condition is met
                if await conditional_action.should_execute(self.page):
                    logger.info(
                        f"✓ Conditional action triggered: {conditional_action.name} "
                        f"(priority: {conditional_action.priority})"
                    )
                    
                    # Execute the conditional action (Requirement 6.2)
                    success, _ = await self.executor.execute(
                        conditional_action, {}
                    )
                    
                    if success:
                        action_executed = True
                        # Wait for page to settle after action
                        await self.rate_limiter.delay_after_page_load()
                        logger.debug("Page state changed, re-evaluating conditions")
                        break  # Re-evaluate from beginning (Requirement 6.3)
                    else:
                        logger.warning(
                            f"Conditional action failed: {conditional_action.name}"
                        )
            
            if not action_executed:
                # No conditional actions matched, proceed with main flow (Requirement 6.4)
                logger.info("No conditional actions matched, proceeding with main flow")
                break
            
            checks_performed += 1
        
        # Enforce max iterations limit (Requirement 6.5)
        if checks_performed >= max_conditional_checks:
            logger.warning(
                f"Max conditional checks ({max_conditional_checks}) reached, "
                f"proceeding with main flow"
            )
        
        # Execute main action flow
        logger.info("Executing main action flow")
        try:
            await self.execute_flow(main_actions)
            return True
        except Exception as e:
            logger.error(f"Main action flow failed: {type(e).__name__}: {e}")
            return False

    async def login(self, email: str, password: str) -> bool:
        """
        Perform login flow using credentials with conditional action support.

        Navigates to LinkedIn login page, handles cookie dialogs and sign-in
        selection automatically, then fills in credentials and submits the
        login form using accessibility-based navigation.

        Args:
            email: LinkedIn email/phone
            password: LinkedIn password

        Returns:
            True if login successful, False otherwise

        Requirements:
            - 1.4: Locate email textbox by ARIA role and accessible name
            - 1.5: Locate password textbox by ARIA role and accessible name
            - 1.6: Locate sign-in button by ARIA role and accessible name
            - 2.1: Verify URL doesn't contain /login after successful login
            - 2.5: Proceed to messaging after successful login
            - 8.1: Check for cookie dialog, sign-in selection, login form in priority order
            - 8.2: Navigate to email/phone login form if on selection page
            - 8.3: Fill credentials and submit
            - 8.4: Skip if already logged in
            - 8.5: Verify successful login
        """
        logger.info("Starting login flow with conditional actions")

        try:
            # Navigate to LinkedIn login page
            await self.page.goto("https://www.linkedin.com/login")
            await self.rate_limiter.delay_after_page_load()

            # Check if already logged in (Requirement 8.4)
            if not await self._is_login_required():
                logger.info("Already logged in, skipping login flow")
                return True

            # Define login actions (Requirements 8.3)
            # LinkedIn uses a two-step login on mobile: email → Continue → password → Sign in.
            # click_continue is optional (execute_flow continues on failure) so it also works
            # when email and password appear on the same page.
            login_actions = [
                Action(
                    name="fill_email",
                    action_type="fill",
                    role="textbox",
                    name_pattern="Email or phone",
                    value=email,
                ),
                Action(
                    name="click_continue",
                    action_type="click",
                    role="button",
                    name_pattern=r"^Continue$",
                ),
                Action(
                    name="fill_password",
                    action_type="fill",
                    role="textbox",
                    name_pattern="Password",
                    value=password,
                ),
                Action(
                    name="click_sign_in",
                    action_type="click",
                    role="button",
                    name_pattern=r"^Sign in$",  # Exact match to avoid matching "Sign in with Apple"
                ),
            ]

            # Import conditional actions
            from dm_bot.actions import get_default_login_conditionals
            
            # Create NavigationEngine with conditional actions if not already set
            # (Requirements 8.1, 8.2)
            if not self.conditional_actions:
                self.conditional_actions = sorted(
                    get_default_login_conditionals(),
                    key=lambda a: a.priority,
                    reverse=True,
                )
                logger.debug(
                    f"Loaded {len(self.conditional_actions)} default login conditional actions"
                )

            # Execute login flow with conditional actions (Requirement 8.1)
            success = await self.execute_with_conditionals(
                main_actions=login_actions,
                max_conditional_checks=5,
            )

            if not success:
                logger.error("Login flow execution failed")
                return False

            # Wait for navigation to complete
            await self.rate_limiter.delay_after_page_load()

            # Verify login success (Requirement 8.5)
            url = self.page.url.lower()
            if "/login" in url:
                logger.error("Login verification failed - still on login page")
                return False

            # Check for checkpoint
            if await self.check_for_checkpoint():
                logger.error("Checkpoint detected after login")
                self.notifier.notify_checkpoint(self.page.url)
                raise CheckpointDetectedError(
                    f"Checkpoint detected at: {self.page.url}"
                )

            logger.info("Login successful")
            return True

        except CheckpointDetectedError:
            # Re-raise checkpoint errors
            raise
        except Exception as e:
            logger.error(f"Login failed with error: {type(e).__name__}: {e}")
            return False

    async def navigate_to_messaging(self) -> bool:
        """
        Navigate from home page to messaging interface.

        Clicks the messaging link and waits for the conversation list to load.

        Returns:
            True if navigation successful, False otherwise

        Requirements:
            - 3.1: Locate messaging link by ARIA role and accessible name
            - 3.2: Click messaging link to navigate
            - 3.3: Wait for conversation list to load
            - 3.4: Verify conversation list contains listitem elements
            - 3.5: Retry navigation on timeout
        """
        logger.info("Navigating to messaging interface")

        try:
            # Define messaging navigation actions
            messaging_actions = [
                Action(
                    name="click_messaging_link",
                    action_type="click",
                    role="link",
                    name_pattern="Messaging.*",
                ),
                Action(
                    name="wait_for_conversation_list",
                    action_type="wait_for",
                    role="list",
                    name_pattern=".*",
                ),
            ]

            # Execute messaging navigation flow
            await self.execute_flow(messaging_actions)

            logger.info("Successfully navigated to messaging interface")
            return True

        except CheckpointDetectedError:
            # Re-raise checkpoint errors
            raise
        except Exception as e:
            logger.error(
                f"Failed to navigate to messaging: {type(e).__name__}: {e}"
            )
            return False

    async def _is_login_required(self) -> bool:
        """
        Check if login is required based on current URL.

        Returns:
            True if URL contains /login, False otherwise

        Requirement 2.1: URL-based login state detection
        """
        url = self.page.url.lower()
        return "/login" in url
