"""Action system for accessibility-based navigation.

This module provides declarative action definitions and execution logic
for interacting with web pages through the accessibility tree.

Requirements: 1.4, 1.5, 1.6, 3.1, 7.1, 7.2
"""

import asyncio
import logging
import re
from typing import Any, Awaitable, Callable, Optional

from playwright.async_api import Locator, Page
from pydantic import BaseModel, ConfigDict

from dm_bot.config import DEFAULT_TIMEOUT_MS, RateLimiter, calculate_backoff_delay, MAX_RETRY_ATTEMPTS

logger = logging.getLogger(__name__)


# ============================================================================
# Custom Exception Classes (Requirement 5.1, 5.2, 5.3, 5.4, 5.5)
# ============================================================================

class CheckpointDetectedError(Exception):
    """
    Raised when LinkedIn presents a security verification page.
    
    This error requires manual user intervention and should stop all automation.
    No retry should be attempted.
    
    Requirement: 2.2, 2.3, 2.4
    """
    pass


class NavigationTimeoutError(Exception):
    """
    Raised when page navigation exceeds timeout.
    
    This error should trigger a retry with exponential backoff.
    
    Requirement: 5.3
    """
    pass


class ElementNotFoundError(Exception):
    """
    Raised when accessibility tree query returns no matches.
    
    This error should trigger retry with exponential backoff (up to 3 times).
    
    Requirement: 5.1
    """
    pass


class RateLimitExceededError(Exception):
    """
    Raised when action rate exceeds threshold.
    
    This error should pause execution for calculated duration.
    
    Requirement: 4.5
    """
    pass


class FatalError(Exception):
    """
    Catch-all for unexpected errors.
    
    This error should close browser cleanly, send notification, and exit.
    
    Requirement: 5.5
    """
    pass


class Action(BaseModel):
    """
    Declarative action definition for accessibility-based navigation.

    Actions describe interactions with web page elements using ARIA roles
    and accessible names, making navigation resilient to UI changes.

    Attributes:
        name: Human-readable identifier for the action
        action_type: Type of action ('wait_for', 'click', 'fill', 'check')
        role: ARIA role of the target element (e.g., 'button', 'textbox', 'link')
        name_pattern: Regex or exact match for accessible name
        value: Value to fill (for 'fill' actions)
        timeout_ms: Element wait timeout in milliseconds
        on_success: Name of next action to execute on success
        on_failure: Name of action to execute on failure
        handler: Custom handler function for complex actions
        extract_to: Context key to store extracted data
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    action_type: str
    role: Optional[str] = None
    name_pattern: Optional[str] = None
    value: Optional[str] = None
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    on_success: Optional[str] = None
    on_failure: Optional[str] = None
    handler: Optional[Callable] = None
    extract_to: Optional[str] = None


class ConditionalAction(Action):
    """
    An action that only executes if a condition is met.

    Extends Action with conditional execution and priority ordering.
    Inherits all fields from Action (name, action_type, role, name_pattern, etc.)

    Attributes:
        condition_check: Async function that checks if action should execute
        priority: Higher priority = checked first (default: 0)

    Requirements:
        - 7.1: Support condition_check callable that returns True if action should execute
        - 7.2: Support priority integer (higher = checked first)
        - 7.3: Support same action types as regular actions
    """

    condition_check: Optional[Callable[[Page], Awaitable[bool]]] = None
    priority: int = 0
    
    async def should_execute(self, page: Page) -> bool:
        """
        Check if this action's condition is met.
        
        Args:
            page: Playwright page object
            
        Returns:
            True if condition is met and action should execute, False otherwise
            
        Requirement 7.1: Support condition_check callable
        """
        if self.condition_check is None:
            logger.warning(f"ConditionalAction {self.name} has no condition_check, defaulting to False")
            return False
        
        try:
            return await self.condition_check(page)
        except Exception as e:
            logger.warning(f"Condition check failed for {self.name}: {e}")
            return False


class ActionExecutor:
    """
    Executes actions against web pages using accessibility tree navigation.
    
    All element interactions use ARIA roles and accessible names rather than
    CSS selectors, making the system resilient to UI changes (Requirement 7.1).
    """
    
    def __init__(self, page: Page, rate_limiter: RateLimiter):
        """
        Initialize action executor.
        
        Args:
            page: Playwright page object
            rate_limiter: Rate limiter for human-like delays
        """
        self.page = page
        self.rate_limiter = rate_limiter
    
    async def execute(
        self,
        action: Action,
        context: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """
        Execute a single action with retry logic and exponential backoff.
        
        Args:
            action: Action to execute
            context: Shared context dictionary for passing data between actions
            
        Returns:
            Tuple of (success: bool, updated_context: dict)
            
        Requirements:
            - 1.4: Locate email textbox by ARIA role and accessible name
            - 1.5: Locate password textbox by ARIA role and accessible name
            - 1.6: Locate sign-in button by ARIA role and accessible name
            - 3.1: Locate messaging link by ARIA role and accessible name
            - 7.1: Use get_by_role method with ARIA role and accessible name
            - 5.1: Retry up to 3 times with exponential backoff
            - 5.2: Use backoff formula: 5.0 × (2 ^ attempt)
            - 5.3: Retry on element not found or timeout
            - 5.4: Invoke failure handler after retry exhaustion
        """
        logger.info(
            f"Executing action: {action.name} (type: {action.action_type})"
        )
        
        # Attempt execution with retry logic (Requirement 5.1)
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                # Dispatch to appropriate handler based on action type
                if action.handler:
                    # Custom handler function
                    success = await action.handler(self.page, context)
                elif action.action_type == "wait_for":
                    success = await self._handle_wait_for(action, context)
                elif action.action_type == "click":
                    success = await self._handle_click(action, context)
                elif action.action_type == "fill":
                    success = await self._handle_fill(action, context)
                elif action.action_type == "check":
                    success = await self._handle_check(action, context)
                else:
                    logger.error(f"Unknown action type: {action.action_type}")
                    return False, context
                
                if success:
                    logger.info(f"Action succeeded: {action.name}")
                    return success, context
                else:
                    # Action returned False, treat as failure
                    if attempt < MAX_RETRY_ATTEMPTS - 1:
                        logger.warning(
                            f"Action failed: {action.name} (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS})"
                        )
                        # Calculate and apply exponential backoff (Requirement 5.2)
                        delay = calculate_backoff_delay(attempt)
                        logger.warning(f"Retrying after {delay} seconds...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"Action failed after {MAX_RETRY_ATTEMPTS} attempts: {action.name}"
                        )
                
            except (ElementNotFoundError, NavigationTimeoutError, TimeoutError) as e:
                # Retryable errors (Requirement 5.3)
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    logger.warning(
                        f"Action {action.name} raised {type(e).__name__}: {e} "
                        f"(attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS})"
                    )
                    # Calculate and apply exponential backoff (Requirement 5.2)
                    delay = calculate_backoff_delay(attempt)
                    logger.warning(f"Retrying after {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Action {action.name} failed after {MAX_RETRY_ATTEMPTS} attempts: "
                        f"{type(e).__name__}: {e}"
                    )
                    
            except CheckpointDetectedError:
                # Non-retryable error - re-raise immediately
                logger.error(f"Checkpoint detected during action: {action.name}")
                raise
                
            except Exception as e:
                # Unexpected error
                logger.error(
                    f"Action {action.name} raised unexpected exception: "
                    f"{type(e).__name__}: {e}"
                )
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    delay = calculate_backoff_delay(attempt)
                    logger.warning(f"Retrying after {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Action {action.name} failed after {MAX_RETRY_ATTEMPTS} attempts"
                    )
        
        # All retry attempts exhausted (Requirement 5.4)
        logger.error(
            f"Action {action.name} exhausted all retry attempts, invoking failure handler"
        )
        
        # Invoke failure handler if specified (Requirement 5.4)
        if action.on_failure:
            logger.info(f"Invoking failure handler: {action.on_failure}")
            context["last_failed_action"] = action.name
        
        return False, context
    
    async def _handle_wait_for(
        self,
        action: Action,
        context: dict[str, Any],
    ) -> bool:
        """Handle 'wait_for' action type."""
        if not action.role or not action.name_pattern:
            logger.error("wait_for action requires role and name_pattern")
            return False
        
        try:
            locator = await self.wait_for_element(
                role=action.role,
                name_pattern=action.name_pattern,
                timeout_ms=action.timeout_ms,
            )
            
            # Store locator in context if extract_to is specified
            if action.extract_to:
                context[action.extract_to] = locator
            
            return True
        except Exception as e:
            logger.warning(
                f"wait_for failed for {action.role} '{action.name_pattern}': {e}"
            )
            return False
    
    async def _handle_click(
        self,
        action: Action,
        context: dict[str, Any],
    ) -> bool:
        """Handle 'click' action type."""
        if not action.role or not action.name_pattern:
            logger.error("click action requires role and name_pattern")
            return False
        
        return await self.click_element(
            role=action.role,
            name_pattern=action.name_pattern,
            timeout_ms=action.timeout_ms,
        )
    
    async def _handle_fill(
        self,
        action: Action,
        context: dict[str, Any],
    ) -> bool:
        """Handle 'fill' action type."""
        if not action.role or not action.name_pattern:
            logger.error("fill action requires role and name_pattern")
            return False
        
        if action.value is None:
            logger.error("fill action requires value")
            return False
        
        return await self.fill_element(
            role=action.role,
            name_pattern=action.name_pattern,
            value=action.value,
            timeout_ms=action.timeout_ms,
        )
    
    async def _handle_check(
        self,
        action: Action,
        context: dict[str, Any],
    ) -> bool:
        """Handle 'check' action type for verification."""
        if not action.role or not action.name_pattern:
            logger.error("check action requires role and name_pattern")
            return False
        
        try:
            # Check if element exists without throwing
            locator = self._get_locator(action.role, action.name_pattern)
            count = await locator.count()
            
            if count > 0:
                logger.info(
                    f"Check passed: found {count} element(s) with role "
                    f"'{action.role}' and name '{action.name_pattern}'"
                )
                return True
            else:
                logger.info(
                    f"Check failed: no elements with role '{action.role}' "
                    f"and name '{action.name_pattern}'"
                )
                return False
        except Exception as e:
            logger.warning(f"Check failed with exception: {e}")
            return False
    
    async def wait_for_element(
        self,
        role: str,
        name_pattern: str,
        timeout_ms: int,
    ) -> Locator:
        """
        Wait for element with role and name to appear.
        
        Uses Playwright's get_by_role method with ARIA role and accessible name
        (Requirement 7.1). Supports regex pattern matching (Requirement 7.2).
        
        Args:
            role: ARIA role (e.g., 'button', 'textbox', 'link')
            name_pattern: Regex or exact match for accessible name
            timeout_ms: Timeout in milliseconds
            
        Returns:
            Locator for the element
            
        Raises:
            ElementNotFoundError: If element not found within timeout
            CheckpointDetectedError: If checkpoint is detected (re-raised)
        """
        logger.debug(
            f"Waiting for element: role='{role}', name='{name_pattern}', "
            f"timeout={timeout_ms}ms"
        )
        
        locator = self._get_locator(role, name_pattern)
        
        try:
            # Wait for element to be visible
            await locator.wait_for(state="visible", timeout=timeout_ms)
            
            logger.debug(f"Element found: role='{role}', name='{name_pattern}'")
            return locator
        except CheckpointDetectedError:
            # Re-raise checkpoint errors without conversion
            raise
        except Exception as e:
            # Convert timeout to ElementNotFoundError for retry logic
            raise ElementNotFoundError(
                f"Element not found: role='{role}', name='{name_pattern}'"
            ) from e
    
    async def click_element(
        self,
        role: str,
        name_pattern: str,
        timeout_ms: int,
    ) -> bool:
        """
        Click element matching role and name.
        
        Uses accessibility-based navigation (Requirement 7.1) with regex
        pattern matching support (Requirement 7.2).
        
        Args:
            role: ARIA role
            name_pattern: Regex or exact match for accessible name
            timeout_ms: Timeout in milliseconds
            
        Returns:
            True if click succeeded, False otherwise
        """
        try:
            locator = await self.wait_for_element(role, name_pattern, timeout_ms)
            
            # Apply rate limiting delay before action
            await self.rate_limiter.delay_between_actions()
            
            await locator.click()
            
            logger.info(
                f"Clicked element: role='{role}', name='{name_pattern}'"
            )
            return True
            
        except Exception as e:
            logger.warning(
                f"Failed to click element: role='{role}', "
                f"name='{name_pattern}': {e}"
            )
            return False
    
    async def fill_element(
        self,
        role: str,
        name_pattern: str,
        value: str,
        timeout_ms: int,
    ) -> bool:
        """
        Fill textbox with value using human-like typing.
        
        Uses accessibility-based navigation (Requirement 7.1) with regex
        pattern matching support (Requirement 7.2). Applies per-character
        typing delays (Requirement 4.2).
        
        Args:
            role: ARIA role (typically 'textbox')
            name_pattern: Regex or exact match for accessible name
            value: Text to fill
            timeout_ms: Timeout in milliseconds
            
        Returns:
            True if fill succeeded, False otherwise
        """
        try:
            locator = await self.wait_for_element(role, name_pattern, timeout_ms)
            
            # Apply rate limiting delay before action
            await self.rate_limiter.delay_between_actions()
            
            # Clear existing value
            await locator.clear()
            
            # Type with human-like delays (Requirement 4.2)
            for char in value:
                await locator.type(char)
                # Delay is handled per-character by the typing
                await self.rate_limiter.delay_for_typing(char)
            
            logger.info(
                f"Filled element: role='{role}', name='{name_pattern}' "
                f"with {len(value)} characters"
            )
            return True
            
        except Exception as e:
            logger.warning(
                f"Failed to fill element: role='{role}', "
                f"name='{name_pattern}': {e}"
            )
            return False
    
    def _get_locator(self, role: str, name_pattern: str) -> Locator:
        """
        Get locator for element using ARIA role and accessible name.
        
        Supports both exact string matching and regex patterns (Requirement 7.2).
        Never falls back to CSS selectors (Requirement 7.4).
        
        Args:
            role: ARIA role
            name_pattern: Regex or exact match for accessible name
            
        Returns:
            Locator for the element(s)
        """
        # Try to compile as regex to check if it's a valid regex pattern
        # If it fails, treat as exact string match
        try:
            # Check if name_pattern contains regex metacharacters
            regex_chars = r'[.*+?^${}()|[\]\\]'
            if re.search(regex_chars, name_pattern):
                # Try to compile as regex
                pattern = re.compile(name_pattern)
                locator = self.page.get_by_role(role, name=pattern)  # type: ignore[arg-type]
            else:
                # No regex chars, treat as exact string match
                locator = self.page.get_by_role(role, name=name_pattern)  # type: ignore[arg-type]
        except re.error:
            # Invalid regex, treat as exact string match
            locator = self.page.get_by_role(role, name=name_pattern)  # type: ignore[arg-type]
        
        return locator
    
    async def get_all_matching_elements(
        self,
        role: str,
        name_pattern: str,
        timeout_ms: int,
    ) -> list[Locator]:
        """
        Get all elements matching role and name.
        
        Supports multiple element matching (Requirement 7.3) for iteration
        over collections like conversation lists.
        
        Args:
            role: ARIA role
            name_pattern: Regex or exact match for accessible name
            timeout_ms: Timeout in milliseconds
            
        Returns:
            List of locators for all matching elements
        """
        try:
            locator = self._get_locator(role, name_pattern)
            
            # Wait for at least one element to appear
            await locator.first.wait_for(state="visible", timeout=timeout_ms)
            
            # Get count of matching elements
            count = await locator.count()
            
            logger.info(
                f"Found {count} elements: role='{role}', name='{name_pattern}'"
            )
            
            # Return list of individual locators
            return [locator.nth(i) for i in range(count)]
            
        except Exception as e:
            logger.warning(
                f"Failed to get matching elements: role='{role}', "
                f"name='{name_pattern}': {e}"
            )
            return []


# ============================================================================
# Action Flow Definitions (Requirement 1.4, 1.5, 1.6, 3.1, 3.3, 3.4)
# ============================================================================

def check_login_state_handler(page: Page, context: dict[str, Any]) -> bool:
    """
    Custom handler to check if user is logged in by verifying URL.
    
    Requirement 2.1: Verify current URL does not contain "/login"
    
    Args:
        page: Playwright page object
        context: Shared context dictionary
        
    Returns:
        True if logged in (URL does not contain "/login"), False otherwise
    """
    url = page.url.lower()
    is_logged_in = "/login" not in url
    
    if is_logged_in:
        logger.info(f"Login state check passed: URL does not contain '/login' ({url})")
    else:
        logger.warning(f"Login state check failed: URL contains '/login' ({url})")
    
    context["logged_in"] = is_logged_in
    return is_logged_in


# Login Flow Actions
# Requirements: 1.4, 1.5, 1.6
LOGIN_FLOW = [
    Action(
        name="wait_for_email_field",
        action_type="wait_for",
        role="textbox",
        name_pattern="Email or phone",
        timeout_ms=10000,
    ),
    Action(
        name="fill_email_field",
        action_type="fill",
        role="textbox",
        name_pattern="Email or phone",
        value=None,  # Will be set dynamically from context
        timeout_ms=10000,
    ),
    Action(
        name="wait_for_password_field",
        action_type="wait_for",
        role="textbox",
        name_pattern="Password",
        timeout_ms=10000,
    ),
    Action(
        name="fill_password_field",
        action_type="fill",
        role="textbox",
        name_pattern="Password",
        value=None,  # Will be set dynamically from context
        timeout_ms=10000,
    ),
    Action(
        name="click_sign_in_button",
        action_type="click",
        role="button",
        name_pattern="Sign in",
        timeout_ms=10000,
    ),
]


# Navigate to Messaging Flow Actions
# Requirements: 3.1, 3.3, 3.4
NAVIGATE_TO_MESSAGING_FLOW = [
    Action(
        name="wait_for_messaging_link",
        action_type="wait_for",
        role="link",
        name_pattern="Messaging.*",  # Regex pattern to match "Messaging" with any suffix
        timeout_ms=10000,
    ),
    Action(
        name="click_messaging_link",
        action_type="click",
        role="link",
        name_pattern="Messaging.*",
        timeout_ms=10000,
    ),
    Action(
        name="wait_for_conversation_list",
        action_type="wait_for",
        role="list",
        name_pattern=".*",  # Match any list element
        timeout_ms=10000,
    ),
]


# Check Login State Actions
# Requirement: 2.1
CHECK_LOGIN_STATE = [
    Action(
        name="check_login_state",
        action_type="check",
        role=None,
        name_pattern=None,
        handler=check_login_state_handler,
        timeout_ms=5000,
    ),
]


# ============================================================================
# Predefined Conditional Actions (Requirements 4, 5, 7, 8)
# ============================================================================

# Priority levels for conditional actions
PRIORITY_CRITICAL = 100  # Cookie dialogs, security warnings
PRIORITY_HIGH = 50       # Sign-in selection, navigation blockers
PRIORITY_NORMAL = 0      # Optional optimizations


def get_cookie_dialog_action() -> "ConditionalAction":
    """
    Get the cookie dialog conditional action.
    
    This function creates the action lazily to avoid circular imports.
    Based on actual LinkedIn accessibility dumps (linkedin_home_20260201_131305.json),
    the cookie dialog has a button with exact name "Accept".
    
    Returns:
        ConditionalAction for handling cookie consent dialogs
        
    Requirements:
        - 4.1: Detect cookie consent dialog by checking for cookie-related buttons
        - 4.2: Click accept button when cookie dialog is detected
    """
    from dm_bot.navigation import has_cookie_dialog
    
    return ConditionalAction(
        name="accept_cookies",
        action_type="click",
        role="button",
        name_pattern=r"^Accept$",  # Exact match based on actual dumps (task 11.1)
        priority=PRIORITY_CRITICAL,
        condition_check=has_cookie_dialog,
        timeout_ms=5000,
    )


def get_signin_selection_action() -> "ConditionalAction":
    """
    Get the sign-in selection conditional action.
    
    This function creates the action lazily to avoid circular imports.
    
    Returns:
        ConditionalAction for handling sign-in method selection
        
    Requirements:
        - 5.1: Detect sign-in method selection page
        - 5.2: Click "Sign in with email" link when selection page is detected
    """
    from dm_bot.navigation import has_signin_selection
    
    return ConditionalAction(
        name="select_email_signin",
        action_type="click",
        role="link",
        name_pattern=r"Sign in with email",
        priority=PRIORITY_HIGH,
        condition_check=has_signin_selection,
        timeout_ms=10000,
    )


def get_default_login_conditionals() -> list["ConditionalAction"]:
    """
    Get the default conditional actions for login flows.
    
    Returns:
        List of conditional actions for handling common login page states
        
    Requirements:
        - 8.1: Check for cookie dialog, sign-in selection, and login form in priority order
    """
    return [
        get_cookie_dialog_action(),
        get_signin_selection_action(),
    ]
