"""Property-based tests for Navigation Engine.

Feature: linkedin-navigation
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from hypothesis import given, strategies as st, settings

from dm_bot.navigation import NavigationEngine
from dm_bot.config import RateLimiter
from dm_bot.notifications import NotificationService


# Strategy for generating URLs with and without /login
def url_strategy():
    """Generate URLs that may or may not contain /login."""
    base_urls = st.sampled_from([
        "https://www.linkedin.com",
        "https://www.linkedin.com/feed",
        "https://www.linkedin.com/messaging",
        "https://www.linkedin.com/in/profile",
        "https://www.linkedin.com/jobs",
    ])
    
    # Generate URLs with or without /login
    return st.one_of(
        base_urls,
        st.builds(lambda base: f"{base}/login", base_urls),
        st.just("https://www.linkedin.com/login"),
        st.just("https://www.linkedin.com/uas/login"),
    )


# Feature: linkedin-navigation, Property 2: URL-based login state detection
# Validates: Requirements 2.1
@settings(max_examples=100, deadline=None)
@given(url=url_strategy())
def test_property_2_url_based_login_state_detection(url: str) -> None:
    """
    Property 2: URL-based login state detection
    
    For any URL, the login state check should return false (not logged in)
    if and only if the URL contains "/login".
    
    This test verifies that _is_login_required() correctly identifies
    login pages based on URL patterns.
    """
    async def run_test():
        # Create mock page with the test URL
        mock_page = MagicMock()
        mock_page.url = url
        
        # Create rate limiter and notifier
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        notifier = NotificationService()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Check if login is required
        login_required = await engine._is_login_required()
        
        # Verify the result matches the URL pattern
        url_lower = url.lower()
        expected_login_required = "/login" in url_lower
        
        assert login_required == expected_login_required, (
            f"For URL '{url}': expected login_required={expected_login_required}, "
            f"got {login_required}"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 2: URL-based login state detection
# Validates: Requirements 2.1
@settings(max_examples=100, deadline=None)
@given(
    path=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(min_codepoint=97, max_codepoint=122)
    ),
)
def test_property_2_non_login_urls_return_false(path: str) -> None:
    """
    Property 2: URL-based login state detection
    
    For any URL that does NOT contain "/login", _is_login_required()
    should return False.
    """
    async def run_test():
        # Ensure path doesn't contain "login"
        if "login" in path.lower():
            # Skip this test case
            return
        
        # Create URL without /login
        url = f"https://www.linkedin.com/{path}"
        
        # Create mock page
        mock_page = MagicMock()
        mock_page.url = url
        
        # Create rate limiter and notifier
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        notifier = NotificationService()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Check if login is required
        login_required = await engine._is_login_required()
        
        # Should return False for non-login URLs
        assert login_required is False, (
            f"For non-login URL '{url}', expected login_required=False, "
            f"got {login_required}"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 2: URL-based login state detection
# Validates: Requirements 2.1
def test_property_2_login_url_variations() -> None:
    """
    Property 2: URL-based login state detection
    
    Tests specific login URL variations to ensure they are all detected.
    """
    async def run_test():
        login_urls = [
            "https://www.linkedin.com/login",
            "https://www.linkedin.com/uas/login",
            "https://www.linkedin.com/checkpoint/login",
            "https://www.linkedin.com/login?fromSignIn=true",
            "https://www.linkedin.com/LOGIN",  # Case insensitive
            "https://www.linkedin.com/Login",  # Mixed case
        ]
        
        for url in login_urls:
            # Create mock page
            mock_page = MagicMock()
            mock_page.url = url
            
            # Create rate limiter and notifier
            rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
            notifier = NotificationService()
            
            # Create navigation engine
            engine = NavigationEngine(
                page=mock_page,
                rate_limiter=rate_limiter,
                notifier=notifier,
            )
            
            # Check if login is required
            login_required = await engine._is_login_required()
            
            # Should return True for all login URLs
            assert login_required is True, (
                f"For login URL '{url}', expected login_required=True, "
                f"got {login_required}"
            )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 2: URL-based login state detection
# Validates: Requirements 2.1
def test_property_2_non_login_url_variations() -> None:
    """
    Property 2: URL-based login state detection
    
    Tests specific non-login URL variations to ensure they are NOT
    incorrectly detected as login pages.
    """
    async def run_test():
        non_login_urls = [
            "https://www.linkedin.com/feed",
            "https://www.linkedin.com/messaging",
            "https://www.linkedin.com/in/johndoe",
            "https://www.linkedin.com/jobs",
            "https://www.linkedin.com/",
            "https://www.linkedin.com/checkpoint",  # checkpoint but not login
            "https://www.linkedin.com/authwall",
        ]
        
        for url in non_login_urls:
            # Create mock page
            mock_page = MagicMock()
            mock_page.url = url
            
            # Create rate limiter and notifier
            rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
            notifier = NotificationService()
            
            # Create navigation engine
            engine = NavigationEngine(
                page=mock_page,
                rate_limiter=rate_limiter,
                notifier=notifier,
            )
            
            # Check if login is required
            login_required = await engine._is_login_required()
            
            # Should return False for non-login URLs
            assert login_required is False, (
                f"For non-login URL '{url}', expected login_required=False, "
                f"got {login_required}"
            )
    
    asyncio.run(run_test())



# Strategy for generating checkpoint URLs
def checkpoint_url_strategy():
    """Generate URLs that may or may not contain checkpoint patterns."""
    base_urls = st.sampled_from([
        "https://www.linkedin.com",
        "https://www.linkedin.com/feed",
        "https://www.linkedin.com/messaging",
        "https://www.linkedin.com/in/profile",
    ])
    
    checkpoint_patterns = st.sampled_from([
        "/checkpoint/",
        "/authwall",
    ])
    
    # Generate URLs with or without checkpoint patterns
    return st.one_of(
        base_urls,
        st.builds(lambda base, pattern: f"{base}{pattern}", base_urls, checkpoint_patterns),
        st.just("https://www.linkedin.com/checkpoint/challenge"),
        st.just("https://www.linkedin.com/authwall"),
    )


# Feature: linkedin-navigation, Property 3: Checkpoint detection on abnormal URLs
# Validates: Requirements 2.2, 2.3, 2.4
@settings(max_examples=100, deadline=None)
@given(url=checkpoint_url_strategy())
def test_property_3_checkpoint_detection_on_abnormal_urls(url: str) -> None:
    """
    Property 3: Checkpoint detection on abnormal URLs
    
    For any URL containing "/checkpoint/" or "/authwall", the checkpoint
    detection should return true and trigger automation stop with user
    notification.
    
    This test verifies that check_for_checkpoint() correctly identifies
    checkpoint and authwall URLs.
    """
    async def run_test():
        # Create mock page with the test URL
        mock_page = MagicMock()
        mock_page.url = url
        
        # Create rate limiter and notifier
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        notifier = NotificationService()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Check for checkpoint
        is_checkpoint = await engine.check_for_checkpoint()
        
        # Verify the result matches the URL pattern
        url_lower = url.lower()
        expected_checkpoint = (
            "/checkpoint/" in url_lower
            or "/login" in url_lower
            or "/authwall" in url_lower
        )
        
        assert is_checkpoint == expected_checkpoint, (
            f"For URL '{url}': expected checkpoint={expected_checkpoint}, "
            f"got {is_checkpoint}"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 3: Checkpoint detection on abnormal URLs
# Validates: Requirements 2.2, 2.3, 2.4
@settings(max_examples=100, deadline=None)
@given(
    path=st.text(
        min_size=1,
        max_size=50,
        alphabet=st.characters(min_codepoint=97, max_codepoint=122)
    ),
)
def test_property_3_normal_urls_not_detected_as_checkpoint(path: str) -> None:
    """
    Property 3: Checkpoint detection on abnormal URLs
    
    For any URL that does NOT contain checkpoint patterns, check_for_checkpoint()
    should return False.
    """
    async def run_test():
        # Ensure path doesn't contain checkpoint patterns
        path_lower = path.lower()
        if any(pattern in path_lower for pattern in ["checkpoint", "login", "authwall"]):
            # Skip this test case
            return
        
        # Create URL without checkpoint patterns
        url = f"https://www.linkedin.com/{path}"
        
        # Create mock page
        mock_page = MagicMock()
        mock_page.url = url
        
        # Create rate limiter and notifier
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        notifier = NotificationService()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Check for checkpoint
        is_checkpoint = await engine.check_for_checkpoint()
        
        # Should return False for normal URLs
        assert is_checkpoint is False, (
            f"For normal URL '{url}', expected checkpoint=False, "
            f"got {is_checkpoint}"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 3: Checkpoint detection on abnormal URLs
# Validates: Requirements 2.2, 2.3, 2.4
def test_property_3_checkpoint_url_variations() -> None:
    """
    Property 3: Checkpoint detection on abnormal URLs
    
    Tests specific checkpoint URL variations to ensure they are all detected.
    """
    async def run_test():
        checkpoint_urls = [
            "https://www.linkedin.com/checkpoint/challenge",
            "https://www.linkedin.com/checkpoint/lg/login",
            "https://www.linkedin.com/authwall",
            "https://www.linkedin.com/authwall?trk=bf&trkinfo=",
            "https://www.linkedin.com/CHECKPOINT/challenge",  # Case insensitive
            "https://www.linkedin.com/Authwall",  # Mixed case
        ]
        
        for url in checkpoint_urls:
            # Create mock page
            mock_page = MagicMock()
            mock_page.url = url
            
            # Create rate limiter and notifier
            rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
            notifier = NotificationService()
            
            # Create navigation engine
            engine = NavigationEngine(
                page=mock_page,
                rate_limiter=rate_limiter,
                notifier=notifier,
            )
            
            # Check for checkpoint
            is_checkpoint = await engine.check_for_checkpoint()
            
            # Should return True for all checkpoint URLs
            assert is_checkpoint is True, (
                f"For checkpoint URL '{url}', expected checkpoint=True, "
                f"got {is_checkpoint}"
            )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 3: Checkpoint detection on abnormal URLs
# Validates: Requirements 2.2, 2.3, 2.4
def test_property_3_normal_url_variations() -> None:
    """
    Property 3: Checkpoint detection on abnormal URLs
    
    Tests specific normal URL variations to ensure they are NOT
    incorrectly detected as checkpoints.
    """
    async def run_test():
        normal_urls = [
            "https://www.linkedin.com/feed",
            "https://www.linkedin.com/messaging",
            "https://www.linkedin.com/in/johndoe",
            "https://www.linkedin.com/jobs",
            "https://www.linkedin.com/",
            "https://www.linkedin.com/mynetwork",
            "https://www.linkedin.com/notifications",
        ]
        
        for url in normal_urls:
            # Create mock page
            mock_page = MagicMock()
            mock_page.url = url
            
            # Create rate limiter and notifier
            rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
            notifier = NotificationService()
            
            # Create navigation engine
            engine = NavigationEngine(
                page=mock_page,
                rate_limiter=rate_limiter,
                notifier=notifier,
            )
            
            # Check for checkpoint
            is_checkpoint = await engine.check_for_checkpoint()
            
            # Should return False for normal URLs
            assert is_checkpoint is False, (
                f"For normal URL '{url}', expected checkpoint=False, "
                f"got {is_checkpoint}"
            )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 3: Checkpoint detection on abnormal URLs
# Validates: Requirements 2.2, 2.3, 2.4
def test_property_3_checkpoint_triggers_notification() -> None:
    """
    Property 3: Checkpoint detection on abnormal URLs
    
    Verifies that when a checkpoint is detected during flow execution,
    a notification is sent to the user.
    """
    async def run_test():
        from unittest.mock import patch
        from dm_bot.actions import Action, CheckpointDetectedError
        
        # Create mock page with checkpoint URL
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/checkpoint/challenge"
        mock_page.get_by_role = MagicMock(return_value=MagicMock())
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier and track notification calls
        notifier = NotificationService()
        notification_calls = []
        
        def mock_notify_checkpoint(url):
            notification_calls.append(url)
        
        notifier.notify_checkpoint = mock_notify_checkpoint
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Create a simple action
        actions = [
            Action(
                name="test_action",
                action_type="wait_for",
                role="button",
                name_pattern="Test",
            ),
        ]
        
        # Mock the executor to succeed
        engine.executor.execute = AsyncMock(return_value=(True, {}))
        
        # Execute flow - should detect checkpoint and raise error
        try:
            await engine.execute_flow(actions)
            assert False, "Should have raised CheckpointDetectedError"
        except CheckpointDetectedError:
            # Expected
            pass
        
        # Verify notification was sent
        assert len(notification_calls) == 1, (
            f"Expected 1 notification call, got {len(notification_calls)}"
        )
        assert notification_calls[0] == mock_page.url, (
            f"Expected notification with URL '{mock_page.url}', "
            f"got '{notification_calls[0]}'"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 3: Checkpoint detection on abnormal URLs
# Validates: Requirements 2.2, 2.3, 2.4
def test_property_3_checkpoint_stops_automation() -> None:
    """
    Property 3: Checkpoint detection on abnormal URLs
    
    Verifies that when a checkpoint is detected, automation stops
    by raising CheckpointDetectedError.
    """
    async def run_test():
        from dm_bot.actions import Action, CheckpointDetectedError
        
        # Create mock page with checkpoint URL
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/checkpoint/challenge"
        mock_page.get_by_role = MagicMock(return_value=MagicMock())
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        notifier.notify_checkpoint = MagicMock()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Create multiple actions
        actions = [
            Action(
                name="action_1",
                action_type="wait_for",
                role="button",
                name_pattern="Test1",
            ),
            Action(
                name="action_2",
                action_type="wait_for",
                role="button",
                name_pattern="Test2",
            ),
            Action(
                name="action_3",
                action_type="wait_for",
                role="button",
                name_pattern="Test3",
            ),
        ]
        
        # Track which actions were executed
        executed_actions = []
        
        async def mock_execute(action, context):
            executed_actions.append(action.name)
            return (True, context)
        
        engine.executor.execute = mock_execute
        
        # Execute flow - should stop after first action due to checkpoint
        try:
            await engine.execute_flow(actions)
            assert False, "Should have raised CheckpointDetectedError"
        except CheckpointDetectedError as e:
            # Expected - verify error message contains URL
            assert "checkpoint" in str(e).lower(), (
                f"Error message should mention checkpoint: {e}"
            )
        
        # Verify only the first action was executed (automation stopped)
        assert len(executed_actions) == 1, (
            f"Expected 1 action to execute before stopping, "
            f"got {len(executed_actions)}: {executed_actions}"
        )
        assert executed_actions[0] == "action_1", (
            f"Expected first action to be 'action_1', got '{executed_actions[0]}'"
        )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 7: Priority-based action execution
# Validates: Requirements 6.1, 6.2, 6.4
@settings(max_examples=100, deadline=None)
@given(
    priorities=st.lists(
        st.integers(min_value=0, max_value=100),
        min_size=2,
        max_size=5,
        unique=True,
    )
)
def test_property_7_priority_based_action_execution(priorities: list[int]) -> None:
    """
    Property 7: Priority-based action execution
    
    For any set of conditional actions with distinct priorities, the system
    should check them in descending priority order and stop after the first
    matching condition is executed.
    
    This test verifies that:
    - Conditional actions are checked in priority order (highest first)
    - Only the highest priority matching action is executed
    - Lower priority actions are not checked after a match
    """
    async def run_test():
        from dm_bot.actions import ConditionalAction
        
        # Create mock page
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/feed"
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track which conditions were checked and which actions were executed
        checked_conditions = []
        executed_actions = []
        
        # Track which conditions have been executed (to prevent infinite loop)
        executed_priorities = set()
        
        # Create conditional actions with different priorities
        # Conditions return True only if not yet executed
        conditional_actions = []
        for priority in priorities:
            def make_condition_check(p):
                async def condition_check(page):
                    checked_conditions.append(p)
                    # Only match if not yet executed (prevents infinite loop)
                    return p not in executed_priorities
                return condition_check
            
            conditional_actions.append(
                ConditionalAction(
                    name=f"action_priority_{priority}",
                    action_type="click",
                    role="button",
                    name_pattern="Test",
                    priority=priority,
                    condition_check=make_condition_check(priority),
                )
            )
        
        # Create navigation engine with conditional actions
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=conditional_actions,
        )
        
        # Mock executor to track executions
        async def mock_execute(action, context):
            executed_actions.append(action.priority)
            executed_priorities.add(action.priority)
            return (True, context)
        
        engine.executor.execute = mock_execute
        
        # Create empty main actions
        main_actions = []
        
        # Execute with conditionals
        await engine.execute_with_conditionals(main_actions)
        
        # Verify priorities are sorted correctly (highest first)
        sorted_priorities = sorted(priorities, reverse=True)
        engine_priorities = [a.priority for a in engine.conditional_actions]
        assert engine_priorities == sorted_priorities, (
            f"Expected priorities sorted as {sorted_priorities}, "
            f"got {engine_priorities}"
        )
        
        # Verify only the highest priority action was executed first
        assert len(executed_actions) >= 1, (
            f"Expected at least 1 action to execute, got {len(executed_actions)}"
        )
        
        highest_priority = max(priorities)
        assert executed_actions[0] == highest_priority, (
            f"Expected highest priority action ({highest_priority}) to execute first, "
            f"got {executed_actions[0]}"
        )
        
        # Verify the highest priority condition was checked first
        assert checked_conditions[0] == highest_priority, (
            f"Expected highest priority condition ({highest_priority}) checked first, "
            f"got {checked_conditions[0]}"
        )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 7: Priority-based action execution
# Validates: Requirements 6.1, 6.2, 6.4
def test_property_7_no_match_proceeds_to_main_flow() -> None:
    """
    Property 7: Priority-based action execution
    
    When no conditional actions match, the system should proceed with
    the main action flow without executing any conditional actions.
    """
    async def run_test():
        from dm_bot.actions import ConditionalAction, Action
        
        # Create mock page
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/feed"
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track executions
        executed_actions = []
        
        # Create conditional actions that never match
        async def never_match(page):
            return False
        
        conditional_actions = [
            ConditionalAction(
                name="conditional_1",
                action_type="click",
                role="button",
                name_pattern="Test1",
                priority=100,
                condition_check=never_match,
            ),
            ConditionalAction(
                name="conditional_2",
                action_type="click",
                role="button",
                name_pattern="Test2",
                priority=50,
                condition_check=never_match,
            ),
        ]
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=conditional_actions,
        )
        
        # Mock executor to track executions
        async def mock_execute(action, context):
            executed_actions.append(action.name)
            return (True, context)
        
        engine.executor.execute = mock_execute
        
        # Create main actions
        main_actions = [
            Action(
                name="main_action_1",
                action_type="click",
                role="button",
                name_pattern="Main1",
            ),
            Action(
                name="main_action_2",
                action_type="click",
                role="button",
                name_pattern="Main2",
            ),
        ]
        
        # Execute with conditionals
        result = await engine.execute_with_conditionals(main_actions)
        
        # Verify no conditional actions were executed
        conditional_names = [a.name for a in conditional_actions]
        for name in executed_actions:
            assert name not in conditional_names, (
                f"Conditional action '{name}' should not have been executed"
            )
        
        # Verify main actions were executed
        assert "main_action_1" in executed_actions, (
            "Main action 1 should have been executed"
        )
        assert "main_action_2" in executed_actions, (
            "Main action 2 should have been executed"
        )
        
        # Verify result is True
        assert result is True, "execute_with_conditionals should return True"
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 7: Priority-based action execution
# Validates: Requirements 6.1, 6.2, 6.4
def test_property_7_lower_priority_not_checked_after_match() -> None:
    """
    Property 7: Priority-based action execution
    
    When a high-priority conditional action matches and executes,
    lower-priority actions should not be checked in that iteration.
    """
    async def run_test():
        from dm_bot.actions import ConditionalAction
        
        # Create mock page
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/feed"
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track which conditions were checked
        checked_priorities = []
        executed_priorities = []
        
        # Track if high priority has been executed
        high_priority_executed = False
        
        # Create conditional actions
        # High priority matches once, low priority should not be checked in first iteration
        async def high_priority_check(page):
            nonlocal high_priority_executed
            checked_priorities.append(100)
            # Only match if not yet executed
            return not high_priority_executed
        
        async def low_priority_check(page):
            checked_priorities.append(10)
            return True  # Would match, but shouldn't be checked in first iteration
        
        conditional_actions = [
            ConditionalAction(
                name="high_priority",
                action_type="click",
                role="button",
                name_pattern="High",
                priority=100,
                condition_check=high_priority_check,
            ),
            ConditionalAction(
                name="low_priority",
                action_type="click",
                role="button",
                name_pattern="Low",
                priority=10,
                condition_check=low_priority_check,
            ),
        ]
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=conditional_actions,
        )
        
        # Mock executor to track executions
        async def mock_execute(action, context):
            nonlocal high_priority_executed
            executed_priorities.append(action.priority)
            if action.priority == 100:
                high_priority_executed = True
            return (True, context)
        
        engine.executor.execute = mock_execute
        
        # Execute with conditionals
        await engine.execute_with_conditionals([])
        
        # Verify only high priority was checked in first iteration
        assert 100 in checked_priorities, "High priority should be checked"
        
        # In the first iteration, low priority should NOT be checked
        # because high priority matched and executed
        first_iteration_checks = checked_priorities[:checked_priorities.index(100) + 1]
        assert 10 not in first_iteration_checks, (
            "Low priority should not be checked in first iteration after high priority match"
        )
        
        # Verify high priority was executed at least once
        assert 100 in executed_priorities, (
            "High priority should have been executed"
        )
        
        # Verify high priority was executed first
        assert executed_priorities[0] == 100, (
            f"Expected high priority (100) to execute first, got {executed_priorities[0]}"
        )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 8: Page state re-evaluation
# Validates: Requirements 6.3
def test_property_8_page_state_reevaluation() -> None:
    """
    Property 8: Page state re-evaluation
    
    For any conditional action that changes page state, the system should
    re-evaluate all conditional actions from the beginning rather than
    continuing with lower-priority checks.
    
    This test verifies that after executing a conditional action, the system
    starts checking from the highest priority again.
    """
    async def run_test():
        from dm_bot.actions import ConditionalAction
        
        # Create mock page
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/feed"
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track execution order
        execution_order = []
        check_order = []
        
        # Track which actions have been executed
        executed_actions = set()
        
        # Create conditional actions with different priorities
        # First iteration: high priority matches
        # Second iteration: medium priority matches
        # Third iteration: low priority matches
        async def high_priority_check(page):
            check_order.append("high")
            return "high" not in executed_actions
        
        async def medium_priority_check(page):
            check_order.append("medium")
            return "medium" not in executed_actions
        
        async def low_priority_check(page):
            check_order.append("low")
            return "low" not in executed_actions
        
        conditional_actions = [
            ConditionalAction(
                name="high_priority",
                action_type="click",
                role="button",
                name_pattern="High",
                priority=100,
                condition_check=high_priority_check,
            ),
            ConditionalAction(
                name="medium_priority",
                action_type="click",
                role="button",
                name_pattern="Medium",
                priority=50,
                condition_check=medium_priority_check,
            ),
            ConditionalAction(
                name="low_priority",
                action_type="click",
                role="button",
                name_pattern="Low",
                priority=10,
                condition_check=low_priority_check,
            ),
        ]
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=conditional_actions,
        )
        
        # Mock executor to track executions
        async def mock_execute(action, context):
            if action.name == "high_priority":
                execution_order.append("high")
                executed_actions.add("high")
            elif action.name == "medium_priority":
                execution_order.append("medium")
                executed_actions.add("medium")
            elif action.name == "low_priority":
                execution_order.append("low")
                executed_actions.add("low")
            return (True, context)
        
        engine.executor.execute = mock_execute
        
        # Execute with conditionals
        await engine.execute_with_conditionals([])
        
        # Verify execution order: high, then medium, then low
        assert execution_order == ["high", "medium", "low"], (
            f"Expected execution order ['high', 'medium', 'low'], got {execution_order}"
        )
        
        # Verify that after each execution, checking restarts from the beginning
        # After high executes, we should check high again (which now returns False),
        # then medium (which returns True and executes)
        
        # Find indices where each action was executed
        high_exec_idx = check_order.index("high")
        
        # After high execution, we should see high checked again
        checks_after_high = check_order[high_exec_idx + 1:]
        assert "high" in checks_after_high, (
            "After high priority execution, high priority should be checked again (re-evaluation)"
        )
        
        # The first check after high execution should be high (restart from beginning)
        first_check_after_high = checks_after_high[0]
        assert first_check_after_high == "high", (
            f"After high priority execution, should restart from high priority, "
            f"but got {first_check_after_high}"
        )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 8: Page state re-evaluation
# Validates: Requirements 6.3
@settings(max_examples=100, deadline=None)
@given(
    num_actions=st.integers(min_value=2, max_value=5)
)
def test_property_8_reevaluation_after_any_execution(num_actions: int) -> None:
    """
    Property 8: Page state re-evaluation
    
    For any number of conditional actions, after executing any action,
    the system should re-evaluate from the highest priority.
    """
    async def run_test():
        from dm_bot.actions import ConditionalAction
        
        # Create mock page
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/feed"
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track checks and executions
        check_sequence = []
        executed_priorities = set()
        
        # Create conditional actions
        conditional_actions = []
        for i in range(num_actions):
            priority = (num_actions - i) * 10  # Descending priorities
            
            def make_condition_check(p):
                async def condition_check(page):
                    check_sequence.append(p)
                    return p not in executed_priorities
                return condition_check
            
            conditional_actions.append(
                ConditionalAction(
                    name=f"action_{priority}",
                    action_type="click",
                    role="button",
                    name_pattern=f"Test{priority}",
                    priority=priority,
                    condition_check=make_condition_check(priority),
                )
            )
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=conditional_actions,
        )
        
        # Mock executor
        async def mock_execute(action, context):
            executed_priorities.add(action.priority)
            return (True, context)
        
        engine.executor.execute = mock_execute
        
        # Execute with conditionals
        await engine.execute_with_conditionals([])
        
        # Verify that after each execution, the highest priority is checked again
        highest_priority = max(a.priority for a in conditional_actions)
        
        # Count how many times the highest priority was checked
        highest_checks = check_sequence.count(highest_priority)
        
        # Should be checked at least num_actions times (once per iteration)
        assert highest_checks >= num_actions, (
            f"Highest priority ({highest_priority}) should be checked at least "
            f"{num_actions} times (re-evaluation), but was checked {highest_checks} times"
        )
    
    asyncio.run(run_test())



# Feature: robust-navigation, Property 5: Cookie dialog conditional handling
# Validates: Requirements 4.1, 4.2, 4.3, 4.4
def test_property_5_cookie_dialog_conditional_handling() -> None:
    """
    Property 5: Cookie dialog conditional handling
    
    For any page state, if a cookie dialog is present, the conditional action
    system should detect it, execute the accept action, and then continue with
    the main flow without error.
    
    This test verifies that:
    - Cookie dialog is detected when present
    - Accept button is clicked
    - Main flow continues after handling cookie dialog
    """
    async def run_test():
        from dm_bot.actions import get_cookie_dialog_action, Action
        
        # Create mock page with cookie dialog
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/feed"
        
        # Mock get_by_role to simulate cookie dialog presence
        cookie_button_mock = MagicMock()
        cookie_button_mock.count = AsyncMock(return_value=1)
        cookie_button_mock.wait_for = AsyncMock()
        cookie_button_mock.click = AsyncMock()
        
        def mock_get_by_role(role, name=None):
            if role == "button" and name:
                # Check if it's a cookie-related pattern
                if hasattr(name, 'pattern'):
                    pattern_str = name.pattern
                    if any(word in pattern_str.lower() for word in ['accept', 'reject']):
                        return cookie_button_mock
            return MagicMock(count=AsyncMock(return_value=0))
        
        mock_page.get_by_role = mock_get_by_role
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_between_actions = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track executions
        executed_actions = []
        
        # Get cookie dialog action
        cookie_action = get_cookie_dialog_action()
        
        # Create navigation engine with cookie dialog conditional
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=[cookie_action],
        )
        
        # Track actual executor calls
        async def track_execute(action, context):
            executed_actions.append(action.name)
            # For cookie action, simulate successful click
            if action.name == "accept_cookies":
                return (True, context)
            # For main actions, also succeed
            return (True, context)
        
        engine.executor.execute = track_execute
        
        # Create main actions
        main_actions = [
            Action(
                name="main_action_1",
                action_type="click",
                role="button",
                name_pattern="Main1",
            ),
        ]
        
        # Execute with conditionals
        result = await engine.execute_with_conditionals(main_actions)
        
        # Verify cookie dialog action was executed
        assert "accept_cookies" in executed_actions, (
            "Cookie dialog action should have been executed"
        )
        
        # Verify main action was also executed (flow continued)
        assert "main_action_1" in executed_actions, (
            "Main action should have been executed after cookie dialog"
        )
        
        # Verify cookie action was executed before main action
        cookie_idx = executed_actions.index("accept_cookies")
        main_idx = executed_actions.index("main_action_1")
        assert cookie_idx < main_idx, (
            "Cookie dialog should be handled before main actions"
        )
        
        # Verify result is True
        assert result is True, "execute_with_conditionals should return True"
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 5: Cookie dialog conditional handling
# Validates: Requirements 4.1, 4.2, 4.3, 4.4
def test_property_5_no_cookie_dialog_skips_action() -> None:
    """
    Property 5: Cookie dialog conditional handling
    
    When no cookie dialog is present, the conditional action system should
    skip the cookie handling action without error and proceed with main flow.
    """
    async def run_test():
        from dm_bot.actions import get_cookie_dialog_action, Action
        
        # Create mock page WITHOUT cookie dialog
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/feed"
        
        # Mock get_by_role to simulate NO cookie dialog
        no_element_mock = MagicMock()
        no_element_mock.count = AsyncMock(return_value=0)
        
        mock_page.get_by_role = MagicMock(return_value=no_element_mock)
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track executions
        executed_actions = []
        
        # Get cookie dialog action
        cookie_action = get_cookie_dialog_action()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=[cookie_action],
        )
        
        # Track executor calls
        async def track_execute(action, context):
            executed_actions.append(action.name)
            return (True, context)
        
        engine.executor.execute = track_execute
        
        # Create main actions
        main_actions = [
            Action(
                name="main_action_1",
                action_type="click",
                role="button",
                name_pattern="Main1",
            ),
        ]
        
        # Execute with conditionals
        result = await engine.execute_with_conditionals(main_actions)
        
        # Verify cookie dialog action was NOT executed
        assert "accept_cookies" not in executed_actions, (
            "Cookie dialog action should not execute when no dialog present"
        )
        
        # Verify main action was executed
        assert "main_action_1" in executed_actions, (
            "Main action should have been executed"
        )
        
        # Verify result is True
        assert result is True, "execute_with_conditionals should return True"
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 6: Sign-in selection conditional handling
# Validates: Requirements 5.1, 5.2, 5.3
def test_property_6_signin_selection_conditional_handling() -> None:
    """
    Property 6: Sign-in selection conditional handling
    
    For any page showing the sign-in method selection, the conditional action
    system should detect it, click "Sign in with email", and proceed to the
    login form.
    
    This test verifies that:
    - Sign-in selection page is detected
    - "Sign in with email" link is clicked
    - Flow continues after handling selection
    """
    async def run_test():
        from dm_bot.actions import get_signin_selection_action, Action
        
        # Create mock page with sign-in selection
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/signin-selection"
        
        # Mock get_by_role to simulate sign-in selection presence
        signin_link_mock = MagicMock()
        signin_link_mock.count = AsyncMock(return_value=1)
        signin_link_mock.wait_for = AsyncMock()
        signin_link_mock.click = AsyncMock()
        
        def mock_get_by_role(role, name=None):
            if role == "link" and name:
                # Check if it's sign-in with email pattern
                if hasattr(name, 'pattern'):
                    pattern_str = name.pattern
                    if 'sign in with email' in pattern_str.lower():
                        return signin_link_mock
            return MagicMock(count=AsyncMock(return_value=0))
        
        mock_page.get_by_role = mock_get_by_role
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_between_actions = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track executions
        executed_actions = []
        
        # Get sign-in selection action
        signin_action = get_signin_selection_action()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=[signin_action],
        )
        
        # Track executor calls
        async def track_execute(action, context):
            executed_actions.append(action.name)
            return (True, context)
        
        engine.executor.execute = track_execute
        
        # Create main actions (login form)
        main_actions = [
            Action(
                name="fill_email",
                action_type="fill",
                role="textbox",
                name_pattern="Email or phone",
                value="test@example.com",
            ),
        ]
        
        # Execute with conditionals
        result = await engine.execute_with_conditionals(main_actions)
        
        # Verify sign-in selection action was executed
        assert "select_email_signin" in executed_actions, (
            "Sign-in selection action should have been executed"
        )
        
        # Verify main action was also executed (flow continued)
        assert "fill_email" in executed_actions, (
            "Main action should have been executed after sign-in selection"
        )
        
        # Verify selection action was executed before main action
        selection_idx = executed_actions.index("select_email_signin")
        main_idx = executed_actions.index("fill_email")
        assert selection_idx < main_idx, (
            "Sign-in selection should be handled before main actions"
        )
        
        # Verify result is True
        assert result is True, "execute_with_conditionals should return True"
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 6: Sign-in selection conditional handling
# Validates: Requirements 5.1, 5.2, 5.3
def test_property_6_no_signin_selection_skips_action() -> None:
    """
    Property 6: Sign-in selection conditional handling
    
    When already past the sign-in selection page, the conditional action
    system should skip the selection action without error.
    """
    async def run_test():
        from dm_bot.actions import get_signin_selection_action, Action
        
        # Create mock page WITHOUT sign-in selection (already on login form)
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/feed"
        
        # Mock get_by_role to simulate NO sign-in selection link
        no_element_mock = MagicMock()
        no_element_mock.count = AsyncMock(return_value=0)
        
        mock_page.get_by_role = MagicMock(return_value=no_element_mock)
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track executions
        executed_actions = []
        
        # Get sign-in selection action
        signin_action = get_signin_selection_action()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=[signin_action],
        )
        
        # Track executor calls
        async def track_execute(action, context):
            executed_actions.append(action.name)
            return (True, context)
        
        engine.executor.execute = track_execute
        
        # Create main actions (login form)
        main_actions = [
            Action(
                name="fill_email",
                action_type="fill",
                role="textbox",
                name_pattern="Email or phone",
                value="test@example.com",
            ),
        ]
        
        # Execute with conditionals
        result = await engine.execute_with_conditionals(main_actions)
        
        # Verify sign-in selection action was NOT executed
        assert "select_email_signin" not in executed_actions, (
            "Sign-in selection action should not execute when not on selection page"
        )
        
        # Verify main action was executed
        assert "fill_email" in executed_actions, (
            "Main action should have been executed"
        )
        
        # Verify result is True
        assert result is True, "execute_with_conditionals should return True"
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 5 & 6: Combined cookie and sign-in handling
# Validates: Requirements 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3
def test_property_5_6_combined_cookie_and_signin_handling() -> None:
    """
    Property 5 & 6: Combined cookie and sign-in handling
    
    When both cookie dialog and sign-in selection are present, the system
    should handle them in priority order (cookie first, then sign-in).
    """
    async def run_test():
        from dm_bot.actions import get_default_login_conditionals, Action
        
        # Create mock page
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/signin-selection"
        
        # Track which elements are present (simulate page state changes)
        page_state = {
            'has_cookie': True,
            'has_signin_selection': True,
        }
        
        # Mock get_by_role to simulate both elements
        def mock_get_by_role(role, name=None):
            element_mock = MagicMock()
            
            if role == "button" and name and hasattr(name, 'pattern'):
                pattern_str = name.pattern
                if any(word in pattern_str.lower() for word in ['accept', 'reject']):
                    element_mock.count = AsyncMock(return_value=1 if page_state['has_cookie'] else 0)
                    element_mock.wait_for = AsyncMock()
                    element_mock.click = AsyncMock()
                    return element_mock
            
            if role == "link" and name and hasattr(name, 'pattern'):
                pattern_str = name.pattern
                if 'sign in with email' in pattern_str.lower():
                    element_mock.count = AsyncMock(return_value=1 if page_state['has_signin_selection'] else 0)
                    element_mock.wait_for = AsyncMock()
                    element_mock.click = AsyncMock()
                    return element_mock
            
            element_mock.count = AsyncMock(return_value=0)
            return element_mock
        
        mock_page.get_by_role = mock_get_by_role
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_between_actions = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track executions
        executed_actions = []
        
        # Get default login conditionals (cookie + sign-in)
        conditionals = get_default_login_conditionals()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=conditionals,
        )
        
        # Track executor calls and simulate page state changes
        async def track_execute(action, context):
            executed_actions.append(action.name)
            # After cookie is handled, remove it from page
            if action.name == "accept_cookies":
                page_state['has_cookie'] = False
            # After sign-in selection, remove it from page
            if action.name == "select_email_signin":
                page_state['has_signin_selection'] = False
            return (True, context)
        
        engine.executor.execute = track_execute
        
        # Create main actions
        main_actions = [
            Action(
                name="fill_email",
                action_type="fill",
                role="textbox",
                name_pattern="Email or phone",
                value="test@example.com",
            ),
        ]
        
        # Execute with conditionals
        result = await engine.execute_with_conditionals(main_actions)
        
        # Verify both conditional actions were executed
        assert "accept_cookies" in executed_actions, (
            "Cookie dialog action should have been executed"
        )
        assert "select_email_signin" in executed_actions, (
            "Sign-in selection action should have been executed"
        )
        
        # Verify cookie was handled before sign-in selection (priority order)
        cookie_idx = executed_actions.index("accept_cookies")
        signin_idx = executed_actions.index("select_email_signin")
        assert cookie_idx < signin_idx, (
            "Cookie dialog (priority 100) should be handled before sign-in selection (priority 50)"
        )
        
        # Verify main action was executed last
        assert "fill_email" in executed_actions, (
            "Main action should have been executed"
        )
        main_idx = executed_actions.index("fill_email")
        assert main_idx > cookie_idx and main_idx > signin_idx, (
            "Main action should be executed after all conditional actions"
        )
        
        # Verify result is True
        assert result is True, "execute_with_conditionals should return True"
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 10: Complete login flow with conditionals
# Validates: Requirements 8.1, 8.2, 8.3
def test_property_10_complete_login_flow_with_conditionals() -> None:
    """
    Property 10: Complete login flow with conditionals
    
    For any login attempt, the system should check for cookie dialog, sign-in
    selection, and login form in priority order, executing appropriate actions
    for each detected state.
    
    This test verifies that:
    - Login flow uses execute_with_conditionals
    - Cookie dialog is handled if present
    - Sign-in selection is handled if present
    - Login credentials are filled and submitted
    - Login success is verified by URL check
    """
    async def run_test():
        from dm_bot.actions import Action
        
        # Create mock page
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/login"
        
        # Track page state changes during login flow
        page_state = {
            'has_cookie': True,
            'has_signin_selection': True,
            'on_login_page': True,
        }
        
        # Track navigation calls
        navigation_calls = []
        
        async def mock_goto(url):
            navigation_calls.append(url)
            mock_page.url = url
        
        mock_page.goto = mock_goto
        
        # Mock get_by_role to simulate page elements
        def mock_get_by_role(role, name=None):
            element_mock = MagicMock()
            
            # Cookie dialog button
            if role == "button" and name and hasattr(name, 'pattern'):
                pattern_str = name.pattern
                if any(word in pattern_str.lower() for word in ['accept', 'reject']):
                    element_mock.count = AsyncMock(return_value=1 if page_state['has_cookie'] else 0)
                    element_mock.wait_for = AsyncMock()
                    element_mock.click = AsyncMock()
                    element_mock.clear = AsyncMock()
                    element_mock.type = AsyncMock()
                    return element_mock
            
            # Sign-in selection link
            if role == "link" and name and hasattr(name, 'pattern'):
                pattern_str = name.pattern
                if 'sign in with email' in pattern_str.lower():
                    element_mock.count = AsyncMock(return_value=1 if page_state['has_signin_selection'] else 0)
                    element_mock.wait_for = AsyncMock()
                    element_mock.click = AsyncMock()
                    return element_mock
            
            # Login form fields
            if role == "textbox" and name:
                if isinstance(name, str):
                    name_str = name.lower()
                else:
                    name_str = name.pattern.lower() if hasattr(name, 'pattern') else ""
                
                if 'email' in name_str or 'phone' in name_str or 'password' in name_str:
                    element_mock.count = AsyncMock(return_value=1)
                    element_mock.wait_for = AsyncMock()
                    element_mock.click = AsyncMock()
                    element_mock.clear = AsyncMock()
                    element_mock.type = AsyncMock()
                    return element_mock
            
            # Sign in button
            if role == "button" and name:
                if isinstance(name, str):
                    name_str = name.lower()
                else:
                    name_str = name.pattern.lower() if hasattr(name, 'pattern') else ""
                
                if 'sign in' in name_str:
                    element_mock.count = AsyncMock(return_value=1)
                    element_mock.wait_for = AsyncMock()
                    element_mock.click = AsyncMock()
                    return element_mock
            
            element_mock.count = AsyncMock(return_value=0)
            return element_mock
        
        mock_page.get_by_role = mock_get_by_role
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_between_actions = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        rate_limiter.delay_for_typing = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track all action executions
        executed_actions = []
        
        # Create navigation engine WITHOUT pre-set conditional actions
        # (login method should load them)
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
            conditional_actions=None,
        )
        
        # Track executor calls and simulate page state changes
        async def track_execute(action, context):
            executed_actions.append(action.name)
            
            # Simulate page state changes
            if action.name == "accept_cookies":
                page_state['has_cookie'] = False
            elif action.name == "select_email_signin":
                page_state['has_signin_selection'] = False
            elif action.name == "click_sign_in":
                # After sign in, navigate away from login page
                mock_page.url = "https://www.linkedin.com/feed"
                page_state['on_login_page'] = False
            
            # Return success
            return (True, context)
        
        engine.executor.execute = track_execute
        
        # Mock check_for_checkpoint to avoid false positives during flow
        async def mock_check_checkpoint():
            # Only return True if we're actually on a checkpoint page
            # (not just /login)
            url = mock_page.url.lower()
            return "/checkpoint/" in url or "/authwall" in url
        
        engine.check_for_checkpoint = mock_check_checkpoint
        
        # Execute login flow
        result = await engine.login(
            email="test@example.com",
            password="testpassword123"
        )
        
        # Verify login was successful
        assert result is True, "Login should return True on success"
        
        # Verify navigation to login page occurred
        assert "https://www.linkedin.com/login" in navigation_calls, (
            "Should navigate to login page"
        )
        
        # Verify conditional actions were loaded
        assert len(engine.conditional_actions) > 0, (
            "Login method should load default conditional actions"
        )
        
        # Verify cookie dialog was handled (Requirement 8.1)
        assert "accept_cookies" in executed_actions, (
            "Cookie dialog should be handled during login"
        )
        
        # Verify sign-in selection was handled (Requirement 8.2)
        assert "select_email_signin" in executed_actions, (
            "Sign-in selection should be handled during login"
        )
        
        # Verify login credentials were filled (Requirement 8.3)
        assert "fill_email" in executed_actions, (
            "Email field should be filled"
        )
        assert "fill_password" in executed_actions, (
            "Password field should be filled"
        )
        assert "click_sign_in" in executed_actions, (
            "Sign in button should be clicked"
        )
        
        # Verify execution order: conditionals before main actions
        cookie_idx = executed_actions.index("accept_cookies")
        signin_idx = executed_actions.index("select_email_signin")
        email_idx = executed_actions.index("fill_email")
        
        assert cookie_idx < email_idx, (
            "Cookie dialog should be handled before filling email"
        )
        assert signin_idx < email_idx, (
            "Sign-in selection should be handled before filling email"
        )
        
        # Verify priority order: cookie (100) before sign-in (50)
        assert cookie_idx < signin_idx, (
            "Cookie dialog (priority 100) should be handled before sign-in selection (priority 50)"
        )
        
        # Verify final URL is not login page (Requirement 8.5)
        assert "/login" not in mock_page.url.lower(), (
            f"After successful login, URL should not contain '/login', got: {mock_page.url}"
        )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 10: Complete login flow with conditionals
# Validates: Requirements 8.1, 8.2, 8.3
def test_property_10_login_skips_when_already_logged_in() -> None:
    """
    Property 10: Complete login flow with conditionals
    
    When already logged in (URL does not contain /login), the login method
    should skip the login flow and return True immediately.
    
    This verifies Requirement 8.4: Skip if already logged in.
    """
    async def run_test():
        # Create mock page with non-login URL (already logged in)
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/feed"
        
        # Track navigation calls
        navigation_calls = []
        
        async def mock_goto(url):
            navigation_calls.append(url)
            # Don't change URL - simulate already logged in
        
        mock_page.goto = mock_goto
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.delay_after_page_load = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Track action executions
        executed_actions = []
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Track executor calls
        async def track_execute(action, context):
            executed_actions.append(action.name)
            return (True, context)
        
        engine.executor.execute = track_execute
        
        # Execute login flow
        result = await engine.login(
            email="test@example.com",
            password="testpassword123"
        )
        
        # Verify login returned True
        assert result is True, "Login should return True when already logged in"
        
        # Verify navigation to login page occurred
        assert "https://www.linkedin.com/login" in navigation_calls, (
            "Should still navigate to login page to check state"
        )
        
        # Verify NO actions were executed (skipped login flow)
        assert len(executed_actions) == 0, (
            f"No actions should be executed when already logged in, "
            f"but got: {executed_actions}"
        )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 10: Complete login flow with conditionals
# Validates: Requirements 8.1, 8.2, 8.3
def test_property_10_login_verifies_success_by_url() -> None:
    """
    Property 10: Complete login flow with conditionals
    
    After executing login actions, the system should verify success by
    checking that the URL no longer contains "/login".
    
    This verifies Requirement 8.5: Verify successful login.
    """
    async def run_test():
        # Create mock page
        mock_page = MagicMock()
        mock_page.url = "https://www.linkedin.com/login"
        
        # Track URL changes
        url_history = ["https://www.linkedin.com/login"]
        
        async def mock_goto(url):
            mock_page.url = url
            url_history.append(url)
        
        mock_page.goto = mock_goto
        
        # Mock get_by_role
        def mock_get_by_role(role, name=None):
            element_mock = MagicMock()
            element_mock.count = AsyncMock(return_value=1)
            element_mock.wait_for = AsyncMock()
            element_mock.click = AsyncMock()
            element_mock.clear = AsyncMock()
            element_mock.type = AsyncMock()
            return element_mock
        
        mock_page.get_by_role = mock_get_by_role
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.check_rate_limit = AsyncMock()
        rate_limiter.delay_between_actions = AsyncMock()
        rate_limiter.delay_after_page_load = AsyncMock()
        rate_limiter.delay_for_typing = AsyncMock()
        
        # Create notifier
        notifier = NotificationService()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Track executor calls
        async def mock_execute(action, context):
            # Simulate successful login by changing URL after sign in
            if action.name == "click_sign_in":
                mock_page.url = "https://www.linkedin.com/feed"
                url_history.append(mock_page.url)
            return (True, context)
        
        engine.executor.execute = mock_execute
        
        # Mock check_for_checkpoint to avoid false positives
        async def mock_check_checkpoint():
            url = mock_page.url.lower()
            return "/checkpoint/" in url or "/authwall" in url
        
        engine.check_for_checkpoint = mock_check_checkpoint
        
        # Execute login flow
        result = await engine.login(
            email="test@example.com",
            password="testpassword123"
        )
        
        # Verify login was successful
        assert result is True, "Login should return True when URL changes from /login"
        
        # Verify URL changed from login page
        final_url = url_history[-1]
        assert "/login" not in final_url.lower(), (
            f"Final URL should not contain '/login', got: {final_url}"
        )
        
        # Test failure case: URL still contains /login
        mock_page.url = "https://www.linkedin.com/login"
        
        async def mock_execute_fail(action, context):
            # Don't change URL - simulate failed login
            return (True, context)
        
        engine.executor.execute = mock_execute_fail
        
        # Execute login flow again
        result = await engine.login(
            email="test@example.com",
            password="testpassword123"
        )
        
        # Verify login failed
        assert result is False, (
            "Login should return False when URL still contains '/login'"
        )
    
    asyncio.run(run_test())
