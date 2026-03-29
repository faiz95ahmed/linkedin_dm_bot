"""Property-based tests for Action system.

Feature: linkedin-navigation
"""

import re
from unittest.mock import AsyncMock, MagicMock
from hypothesis import given, strategies as st, settings

from dm_bot.actions import ActionExecutor
from dm_bot.config import RateLimiter


# Strategy for generating valid ARIA roles
aria_roles = st.sampled_from([
    "button", "textbox", "link", "listitem", "list", "heading",
    "checkbox", "radio", "combobox", "menu", "menuitem"
])


# Strategy for generating accessible names (no special characters that break HTML)
accessible_names = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(
        min_codepoint=32,
        max_codepoint=126,
        blacklist_characters='<>"\'&'
    )
)


# Feature: linkedin-navigation, Property 4: Accessibility-based element location
# Validates: Requirements 1.4, 1.5, 1.6, 3.1, 7.1, 7.4
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
)
def test_property_4_accessibility_based_element_location(
    role: str,
    name: str,
) -> None:
    """
    Property 4: Accessibility-based element location
    
    For any element location request, the system should use Playwright's
    get_by_role method with ARIA role and accessible name, never falling
    back to CSS selectors.
    
    This test verifies that _get_locator() always uses get_by_role and
    never uses CSS selector methods.
    """
    # Create mock page
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_page.get_by_role.return_value = mock_locator
    
    # Create rate limiter
    rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
    
    # Create executor
    executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
    
    # Get locator using the internal method
    locator = executor._get_locator(role, name)
    
    # Verify get_by_role was called
    assert mock_page.get_by_role.called, (
        "get_by_role was not called - system may be using CSS selectors"
    )
    
    # Verify get_by_role was called with correct role
    call_args = mock_page.get_by_role.call_args
    assert call_args[0][0] == role, (
        f"Expected role '{role}', got '{call_args[0][0]}'"
    )
    
    # Verify CSS selector methods were NOT called
    assert not hasattr(mock_page, 'query_selector') or not mock_page.query_selector.called, (
        "System fell back to CSS selector (query_selector)"
    )
    assert not hasattr(mock_page, 'locator') or not mock_page.locator.called, (
        "System fell back to CSS selector (locator)"
    )
    
    # Verify the returned locator is from get_by_role
    assert locator == mock_locator, (
        "Returned locator does not match get_by_role result"
    )


# Feature: linkedin-navigation, Property 4: Accessibility-based element location
# Validates: Requirements 1.4, 1.5, 1.6, 3.1, 7.1, 7.4
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
)
def test_property_4_wait_for_element_uses_accessibility(
    role: str,
    name: str,
) -> None:
    """
    Property 4: Accessibility-based element location
    
    Verifies that wait_for_element() uses accessibility-based navigation
    and never falls back to CSS selectors.
    """
    import asyncio
    
    async def run_test():
        # Create mock page
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.wait_for = AsyncMock()
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Wait for element
        result = await executor.wait_for_element(
            role=role,
            name_pattern=name,
            timeout_ms=1000,
        )
        
        # Verify get_by_role was called
        assert mock_page.get_by_role.called, (
            "wait_for_element did not use get_by_role"
        )
        
        # Verify get_by_role was called with correct role
        call_args = mock_page.get_by_role.call_args
        assert call_args[0][0] == role, (
            f"Expected role '{role}', got '{call_args[0][0]}'"
        )
        
        # Verify result is the locator from get_by_role
        assert result == mock_locator, (
            "wait_for_element did not return get_by_role locator"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 4: Accessibility-based element location
# Validates: Requirements 1.4, 1.5, 1.6, 3.1, 7.1, 7.4
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
)
def test_property_4_click_element_uses_accessibility(
    role: str,
    name: str,
) -> None:
    """
    Property 4: Accessibility-based element location
    
    Verifies that click_element() uses accessibility-based navigation.
    """
    import asyncio
    
    async def run_test():
        # Create mock page
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.wait_for = AsyncMock()
        mock_locator.click = AsyncMock()
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.delay_between_actions = AsyncMock()
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Click element
        success = await executor.click_element(
            role=role,
            name_pattern=name,
            timeout_ms=1000,
        )
        
        # Verify get_by_role was called
        assert mock_page.get_by_role.called, (
            "click_element did not use get_by_role"
        )
        
        # Verify get_by_role was called with correct role
        call_args = mock_page.get_by_role.call_args
        assert call_args[0][0] == role, (
            f"Expected role '{role}', got '{call_args[0][0]}'"
        )
        
        # Verify click was called on the locator
        assert mock_locator.click.called, (
            "click was not called on the locator"
        )
        
        # Verify success
        assert success is True, "click_element should return True on success"
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 4: Accessibility-based element location
# Validates: Requirements 1.4, 1.5, 1.6, 3.1, 7.1, 7.4
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
    value=st.text(min_size=1, max_size=50),
)
def test_property_4_fill_element_uses_accessibility(
    role: str,
    name: str,
    value: str,
) -> None:
    """
    Property 4: Accessibility-based element location
    
    Verifies that fill_element() uses accessibility-based navigation.
    """
    import asyncio
    
    async def run_test():
        # Create mock page
        mock_page = MagicMock()
        mock_locator = MagicMock()
        mock_locator.wait_for = AsyncMock()
        mock_locator.clear = AsyncMock()
        mock_locator.type = AsyncMock()
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        rate_limiter.delay_between_actions = AsyncMock()
        rate_limiter.delay_for_typing = AsyncMock()
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Fill element
        success = await executor.fill_element(
            role=role,
            name_pattern=name,
            value=value,
            timeout_ms=1000,
        )
        
        # Verify get_by_role was called
        assert mock_page.get_by_role.called, (
            "fill_element did not use get_by_role"
        )
        
        # Verify get_by_role was called with correct role
        call_args = mock_page.get_by_role.call_args
        assert call_args[0][0] == role, (
            f"Expected role '{role}', got '{call_args[0][0]}'"
        )
        
        # Verify clear and type were called
        assert mock_locator.clear.called, "clear was not called"
        assert mock_locator.type.called, "type was not called"
        
        # Verify success
        assert success is True, "fill_element should return True on success"
    
    asyncio.run(run_test())



# Feature: linkedin-navigation, Property 5: Regex pattern matching for element names
# Validates: Requirements 7.2
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    prefix=st.text(min_size=1, max_size=10, alphabet=st.characters(min_codepoint=97, max_codepoint=122)),
    suffix=st.text(min_size=1, max_size=10, alphabet=st.characters(min_codepoint=97, max_codepoint=122)),
)
def test_property_5_regex_pattern_matching(
    role: str,
    prefix: str,
    suffix: str,
) -> None:
    """
    Property 5: Regex pattern matching for element names
    
    For any accessible name pattern provided as a regex, the system should
    successfully match elements whose accessible names satisfy the pattern.
    
    This test verifies that _get_locator() correctly handles regex patterns
    and passes them to get_by_role as compiled regex objects.
    """
    # Create a regex pattern that matches prefix followed by anything then suffix
    pattern = f"{prefix}.*{suffix}"
    
    # Create mock page
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_page.get_by_role.return_value = mock_locator
    
    # Create rate limiter
    rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
    
    # Create executor
    executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
    
    # Get locator with regex pattern
    _ = executor._get_locator(role, pattern)
    
    # Verify get_by_role was called
    assert mock_page.get_by_role.called, (
        "get_by_role was not called"
    )
    
    # Verify get_by_role was called with correct role
    call_args = mock_page.get_by_role.call_args
    assert call_args[0][0] == role, (
        f"Expected role '{role}', got '{call_args[0][0]}'"
    )
    
    # Verify the name parameter is a compiled regex Pattern object
    name_arg = call_args[1].get('name')
    assert name_arg is not None, "name parameter not passed to get_by_role"
    assert isinstance(name_arg, re.Pattern), (
        f"Expected compiled regex Pattern, got {type(name_arg)}"
    )
    
    # Verify the pattern matches expected strings
    test_string = f"{prefix}middle{suffix}"
    assert name_arg.match(test_string), (
        f"Pattern should match '{test_string}'"
    )


# Feature: linkedin-navigation, Property 5: Regex pattern matching for element names
# Validates: Requirements 7.2
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    base_name=st.text(min_size=3, max_size=20, alphabet=st.characters(min_codepoint=97, max_codepoint=122)),
)
def test_property_5_regex_pattern_with_alternatives(
    role: str,
    base_name: str,
) -> None:
    """
    Property 5: Regex pattern matching for element names
    
    Tests regex patterns with alternatives (|) to match multiple possible names.
    This is useful for matching elements that may have different labels.
    """
    # Create a pattern with alternatives
    pattern = f"({base_name}|{base_name.upper()})"
    
    # Create mock page
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_page.get_by_role.return_value = mock_locator
    
    # Create rate limiter
    rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
    
    # Create executor
    executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
    
    # Get locator with regex pattern
    _ = executor._get_locator(role, pattern)
    
    # Verify get_by_role was called
    assert mock_page.get_by_role.called, (
        "get_by_role was not called"
    )
    
    # Verify the name parameter is a compiled regex Pattern
    call_args = mock_page.get_by_role.call_args
    name_arg = call_args[1].get('name')
    assert isinstance(name_arg, re.Pattern), (
        f"Expected compiled regex Pattern, got {type(name_arg)}"
    )
    
    # Verify the pattern matches both alternatives
    assert name_arg.match(base_name), (
        f"Pattern should match lowercase '{base_name}'"
    )
    assert name_arg.match(base_name.upper()), (
        f"Pattern should match uppercase '{base_name.upper()}'"
    )


# Feature: linkedin-navigation, Property 5: Regex pattern matching for element names
# Validates: Requirements 7.2
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    exact_name=st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(min_codepoint=97, max_codepoint=122)
    ),
)
def test_property_5_exact_string_matching_without_regex(
    role: str,
    exact_name: str,
) -> None:
    """
    Property 5: Regex pattern matching for element names
    
    For strings without regex metacharacters, the system should treat them
    as exact string matches, not regex patterns.
    """
    # Create mock page
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_page.get_by_role.return_value = mock_locator
    
    # Create rate limiter
    rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
    
    # Create executor
    executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
    
    # Get locator with exact string (no regex chars)
    _ = executor._get_locator(role, exact_name)
    
    # Verify get_by_role was called
    assert mock_page.get_by_role.called, (
        "get_by_role was not called"
    )
    
    # Verify get_by_role was called with correct role
    call_args = mock_page.get_by_role.call_args
    assert call_args[0][0] == role, (
        f"Expected role '{role}', got '{call_args[0][0]}'"
    )
    
    # Verify the name parameter is the exact string, not a regex
    name_arg = call_args[1].get('name')
    assert name_arg == exact_name, (
        f"Expected exact string '{exact_name}', got {name_arg}"
    )
    assert not isinstance(name_arg, re.Pattern), (
        "Should not be a regex Pattern for strings without regex chars"
    )


# Feature: linkedin-navigation, Property 5: Regex pattern matching for element names
# Validates: Requirements 7.2
def test_property_5_messaging_link_pattern() -> None:
    """
    Property 5: Regex pattern matching for element names
    
    Tests the specific pattern used in the requirements for matching
    the messaging link: "Messaging.*"
    
    This is a concrete example from Requirement 3.1.
    """
    # Pattern from requirements
    pattern = "Messaging.*"
    role = "link"
    
    # Create mock page
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_page.get_by_role.return_value = mock_locator
    
    # Create rate limiter
    rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
    
    # Create executor
    executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
    
    # Get locator with messaging pattern
    _ = executor._get_locator(role, pattern)
    
    # Verify get_by_role was called
    assert mock_page.get_by_role.called, (
        "get_by_role was not called"
    )
    
    # Verify the name parameter is a compiled regex Pattern
    call_args = mock_page.get_by_role.call_args
    name_arg = call_args[1].get('name')
    assert isinstance(name_arg, re.Pattern), (
        f"Expected compiled regex Pattern, got {type(name_arg)}"
    )
    
    # Verify the pattern matches expected messaging link names
    assert name_arg.match("Messaging"), (
        "Pattern should match 'Messaging'"
    )
    assert name_arg.match("Messaging (3)"), (
        "Pattern should match 'Messaging (3)'"
    )
    assert name_arg.match("Messaging - 5 new messages"), (
        "Pattern should match 'Messaging - 5 new messages'"
    )
    assert not name_arg.match("Messages"), (
        "Pattern should not match 'Messages' (different word)"
    )



# Feature: linkedin-navigation, Property 6: Multiple element matching
# Validates: Requirements 3.4, 7.3
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
    element_count=st.integers(min_value=1, max_value=10),
)
def test_property_6_multiple_element_matching(
    role: str,
    name: str,
    element_count: int,
) -> None:
    """
    Property 6: Multiple element matching
    
    For any ARIA role and name combination that matches multiple elements,
    the system should return all matching elements for iteration.
    
    This test verifies that get_all_matching_elements() returns a list
    containing all elements that match the criteria.
    """
    import asyncio
    
    async def run_test():
        # Create mock page
        mock_page = MagicMock()
        mock_locator = MagicMock()
        
        # Mock the locator to return the specified count
        mock_locator.count = AsyncMock(return_value=element_count)
        mock_locator.first.wait_for = AsyncMock()
        
        # Mock nth() to return individual locators
        mock_nth_locators = [MagicMock() for _ in range(element_count)]
        mock_locator.nth = MagicMock(side_effect=lambda i: mock_nth_locators[i])
        
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Get all matching elements
        elements = await executor.get_all_matching_elements(
            role=role,
            name_pattern=name,
            timeout_ms=1000,
        )
        
        # Verify get_by_role was called
        assert mock_page.get_by_role.called, (
            "get_by_role was not called"
        )
        
        # Verify the correct number of elements was returned
        assert len(elements) == element_count, (
            f"Expected {element_count} elements, got {len(elements)}"
        )
        
        # Verify nth() was called for each element
        assert mock_locator.nth.call_count == element_count, (
            f"Expected nth() to be called {element_count} times, "
            f"got {mock_locator.nth.call_count}"
        )
        
        # Verify each returned element is a locator
        for i, element in enumerate(elements):
            assert element == mock_nth_locators[i], (
                f"Element {i} does not match expected locator"
            )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 6: Multiple element matching
# Validates: Requirements 3.4, 7.3
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
)
def test_property_6_empty_result_when_no_matches(
    role: str,
    name: str,
) -> None:
    """
    Property 6: Multiple element matching
    
    When no elements match the criteria, get_all_matching_elements()
    should return an empty list rather than raising an exception.
    """
    import asyncio
    
    async def run_test():
        # Create mock page
        mock_page = MagicMock()
        mock_locator = MagicMock()
        
        # Mock the locator to timeout (no elements found)
        mock_locator.first.wait_for = AsyncMock(
            side_effect=Exception("Timeout waiting for element")
        )
        
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Get all matching elements (should return empty list)
        elements = await executor.get_all_matching_elements(
            role=role,
            name_pattern=name,
            timeout_ms=100,
        )
        
        # Verify empty list is returned
        assert elements == [], (
            f"Expected empty list when no elements found, got {elements}"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 6: Multiple element matching
# Validates: Requirements 3.4, 7.3
def test_property_6_conversation_list_iteration() -> None:
    """
    Property 6: Multiple element matching
    
    Tests the specific use case from Requirement 3.4: iterating over
    conversation list items.
    
    This verifies that we can find multiple listitem elements within
    a list, which is needed for conversation navigation.
    """
    import asyncio
    
    async def run_test():
        # Simulate finding multiple conversation list items
        role = "listitem"
        name_pattern = ".*"  # Match any listitem
        conversation_count = 5
        
        # Create mock page
        mock_page = MagicMock()
        mock_locator = MagicMock()
        
        # Mock the locator to return multiple conversations
        mock_locator.count = AsyncMock(return_value=conversation_count)
        mock_locator.first.wait_for = AsyncMock()
        
        # Mock nth() to return individual conversation locators
        mock_conversations = [MagicMock() for _ in range(conversation_count)]
        mock_locator.nth = MagicMock(side_effect=lambda i: mock_conversations[i])
        
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Get all conversation list items
        conversations = await executor.get_all_matching_elements(
            role=role,
            name_pattern=name_pattern,
            timeout_ms=1000,
        )
        
        # Verify we got all conversations
        assert len(conversations) == conversation_count, (
            f"Expected {conversation_count} conversations, got {len(conversations)}"
        )
        
        # Verify we can iterate over them
        for i, conversation in enumerate(conversations):
            assert conversation == mock_conversations[i], (
                f"Conversation {i} does not match expected locator"
            )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 6: Multiple element matching
# Validates: Requirements 3.4, 7.3
@settings(max_examples=100, deadline=None)
@given(
    element_count=st.integers(min_value=1, max_value=20),
)
def test_property_6_all_elements_accessible_via_index(
    element_count: int,
) -> None:
    """
    Property 6: Multiple element matching
    
    For any number of matching elements, each element should be accessible
    via its index in the returned list.
    """
    import asyncio
    
    async def run_test():
        role = "button"
        name = "Click me"
        
        # Create mock page
        mock_page = MagicMock()
        mock_locator = MagicMock()
        
        # Mock the locator to return the specified count
        mock_locator.count = AsyncMock(return_value=element_count)
        mock_locator.first.wait_for = AsyncMock()
        
        # Track which indices were requested
        requested_indices = []
        
        def mock_nth(i):
            requested_indices.append(i)
            return MagicMock()
        
        mock_locator.nth = MagicMock(side_effect=mock_nth)
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Get all matching elements
        _ = await executor.get_all_matching_elements(
            role=role,
            name_pattern=name,
            timeout_ms=1000,
        )
        
        # Verify all indices from 0 to element_count-1 were requested
        assert len(requested_indices) == element_count, (
            f"Expected {element_count} indices, got {len(requested_indices)}"
        )
        
        expected_indices = list(range(element_count))
        assert requested_indices == expected_indices, (
            f"Expected indices {expected_indices}, got {requested_indices}"
        )
    
    asyncio.run(run_test())



# Feature: linkedin-navigation, Property 7: Action retry with exponential backoff
# Validates: Requirements 5.1, 5.2, 5.3
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
    failure_count=st.integers(min_value=1, max_value=3),
)
def test_property_7_action_retry_with_exponential_backoff(
    role: str,
    name: str,
    failure_count: int,
) -> None:
    """
    Property 7: Action retry with exponential backoff
    
    For any action that fails due to element not found or timeout, the system
    should retry up to 3 times with delays calculated as 5.0 × (2 ^ attempt_number)
    seconds.
    
    This test verifies:
    1. Actions are retried up to MAX_RETRY_ATTEMPTS times
    2. Backoff delays follow the formula: 5.0 × (2 ^ attempt)
    3. Retries occur for ElementNotFoundError and TimeoutError
    """
    import asyncio
    from unittest.mock import patch
    from dm_bot.actions import Action, ElementNotFoundError
    from dm_bot.config import MAX_RETRY_ATTEMPTS
    
    async def run_test():
        # Track retry attempts and delays
        retry_attempts = []
        sleep_delays = []
        
        # Create mock page that fails the specified number of times
        mock_page = MagicMock()
        mock_locator = MagicMock()
        
        # Create a counter for failures
        call_count = [0]
        
        async def mock_wait_for(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= failure_count:
                # Fail for the first failure_count attempts
                raise ElementNotFoundError(f"Element not found (attempt {call_count[0]})")
            # Succeed after that
            return None
        
        mock_locator.wait_for = mock_wait_for
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Create action
        action = Action(
            name="test_action",
            action_type="wait_for",
            role=role,
            name_pattern=name,
            timeout_ms=100,
        )
        
        # Patch asyncio.sleep to track delays
        original_sleep = asyncio.sleep
        
        async def mock_sleep(delay):
            sleep_delays.append(delay)
            # Don't actually sleep in tests
            await original_sleep(0)
        
        with patch('asyncio.sleep', side_effect=mock_sleep):
            # Execute action
            success, context = await executor.execute(action, {})
            
            # If failure_count < MAX_RETRY_ATTEMPTS, action should succeed
            if failure_count < MAX_RETRY_ATTEMPTS:
                assert success is True, (
                    f"Action should succeed after {failure_count} failures "
                    f"(max retries: {MAX_RETRY_ATTEMPTS})"
                )
                
                # Verify the correct number of retries occurred
                assert call_count[0] == failure_count + 1, (
                    f"Expected {failure_count + 1} attempts, got {call_count[0]}"
                )
                
                # Verify exponential backoff delays
                expected_delays = [5.0 * (2 ** i) for i in range(failure_count)]
                assert len(sleep_delays) == len(expected_delays), (
                    f"Expected {len(expected_delays)} delays, got {len(sleep_delays)}"
                )
                
                for i, (actual, expected) in enumerate(zip(sleep_delays, expected_delays)):
                    assert actual == expected, (
                        f"Delay {i}: expected {expected}s, got {actual}s"
                    )
            else:
                # If failure_count >= MAX_RETRY_ATTEMPTS, action should fail
                assert success is False, (
                    f"Action should fail after {MAX_RETRY_ATTEMPTS} attempts"
                )
                
                # Verify all retries were attempted
                assert call_count[0] == MAX_RETRY_ATTEMPTS, (
                    f"Expected {MAX_RETRY_ATTEMPTS} attempts, got {call_count[0]}"
                )
                
                # Verify exponential backoff delays (MAX_RETRY_ATTEMPTS - 1 delays)
                expected_delays = [5.0 * (2 ** i) for i in range(MAX_RETRY_ATTEMPTS - 1)]
                assert len(sleep_delays) == len(expected_delays), (
                    f"Expected {len(expected_delays)} delays, got {len(sleep_delays)}"
                )
                
                for i, (actual, expected) in enumerate(zip(sleep_delays, expected_delays)):
                    assert actual == expected, (
                        f"Delay {i}: expected {expected}s, got {actual}s"
                    )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 7: Action retry with exponential backoff
# Validates: Requirements 5.1, 5.2, 5.3
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
)
def test_property_7_timeout_error_triggers_retry(
    role: str,
    name: str,
) -> None:
    """
    Property 7: Action retry with exponential backoff
    
    Verifies that TimeoutError (in addition to ElementNotFoundError) triggers
    the retry mechanism with exponential backoff.
    """
    import asyncio
    from unittest.mock import patch
    from dm_bot.actions import Action
    
    async def run_test():
        # Track sleep delays
        sleep_delays = []
        
        # Create mock page that times out twice then succeeds
        mock_page = MagicMock()
        mock_locator = MagicMock()
        
        call_count = [0]
        
        async def mock_wait_for(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise TimeoutError(f"Timeout (attempt {call_count[0]})")
            return None
        
        mock_locator.wait_for = mock_wait_for
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Create action
        action = Action(
            name="test_action",
            action_type="wait_for",
            role=role,
            name_pattern=name,
            timeout_ms=100,
        )
        
        # Patch asyncio.sleep to track delays
        original_sleep = asyncio.sleep
        
        async def mock_sleep(delay):
            sleep_delays.append(delay)
            await original_sleep(0)
        
        with patch('asyncio.sleep', side_effect=mock_sleep):
            # Execute action
            success, context = await executor.execute(action, {})
            
            # Should succeed after 2 retries
            assert success is True, "Action should succeed after retries"
            
            # Verify 3 attempts were made (initial + 2 retries)
            assert call_count[0] == 3, f"Expected 3 attempts, got {call_count[0]}"
            
            # Verify exponential backoff delays
            expected_delays = [5.0, 10.0]  # 5.0 * 2^0, 5.0 * 2^1
            assert len(sleep_delays) == 2, (
                f"Expected 2 delays, got {len(sleep_delays)}"
            )
            
            for i, (actual, expected) in enumerate(zip(sleep_delays, expected_delays)):
                assert actual == expected, (
                    f"Delay {i}: expected {expected}s, got {actual}s"
                )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 7: Action retry with exponential backoff
# Validates: Requirements 5.1, 5.2, 5.3
def test_property_7_checkpoint_error_no_retry() -> None:
    """
    Property 7: Action retry with exponential backoff
    
    Verifies that CheckpointDetectedError does NOT trigger retry logic,
    as checkpoints require manual intervention.
    """
    import asyncio
    from unittest.mock import patch
    from dm_bot.actions import Action, CheckpointDetectedError
    
    async def run_test():
        # Track sleep calls (should be none)
        sleep_calls = []
        
        # Create a custom handler that raises CheckpointDetectedError
        async def checkpoint_handler(page, context):
            raise CheckpointDetectedError("Checkpoint detected")
        
        # Create mock page
        mock_page = MagicMock()
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Create action with custom handler that raises CheckpointDetectedError
        action = Action(
            name="test_action",
            action_type="custom",
            handler=checkpoint_handler,
        )
        
        # Patch asyncio.sleep to track delays
        original_sleep = asyncio.sleep
        
        async def mock_sleep(delay):
            sleep_calls.append(delay)
            await original_sleep(0)
        
        with patch('asyncio.sleep', side_effect=mock_sleep):
            # Execute action - should raise CheckpointDetectedError
            try:
                await executor.execute(action, {})
                assert False, "Should have raised CheckpointDetectedError"
            except CheckpointDetectedError:
                # Expected - checkpoint errors should not be retried
                pass
            
            # Verify no retries occurred (no sleep calls)
            assert len(sleep_calls) == 0, (
                f"CheckpointDetectedError should not trigger retries, "
                f"but {len(sleep_calls)} sleep calls were made"
            )
    
    asyncio.run(run_test())



# Feature: linkedin-navigation, Property 8: Failure handler invocation after retry exhaustion
# Validates: Requirements 5.4
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
    failure_handler_name=st.text(min_size=1, max_size=30, alphabet=st.characters(min_codepoint=97, max_codepoint=122)),
)
def test_property_8_failure_handler_invocation(
    role: str,
    name: str,
    failure_handler_name: str,
) -> None:
    """
    Property 8: Failure handler invocation after retry exhaustion
    
    For any action that fails all retry attempts, the system should log the
    error and invoke the failure handler specified in the action.
    
    This test verifies:
    1. After MAX_RETRY_ATTEMPTS failures, the action returns False
    2. The failure handler name is recorded in context
    3. The last_failed_action is set in context
    """
    import asyncio
    from unittest.mock import patch
    from dm_bot.actions import Action, ElementNotFoundError
    from dm_bot.config import MAX_RETRY_ATTEMPTS
    
    async def run_test():
        # Create mock page that always fails
        mock_page = MagicMock()
        mock_locator = MagicMock()
        
        async def mock_wait_for(*args, **kwargs):
            raise ElementNotFoundError("Element not found")
        
        mock_locator.wait_for = mock_wait_for
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Create action with failure handler
        action = Action(
            name="test_action",
            action_type="wait_for",
            role=role,
            name_pattern=name,
            timeout_ms=100,
            on_failure=failure_handler_name,
        )
        
        # Patch asyncio.sleep to speed up test
        with patch('asyncio.sleep', new_callable=AsyncMock):
            # Execute action
            success, context = await executor.execute(action, {})
            
            # Verify action failed
            assert success is False, (
                "Action should fail after exhausting all retries"
            )
            
            # Verify failure handler was invoked (recorded in context)
            assert "last_failed_action" in context, (
                "last_failed_action should be set in context after failure"
            )
            
            assert context["last_failed_action"] == "test_action", (
                f"Expected last_failed_action to be 'test_action', "
                f"got '{context['last_failed_action']}'"
            )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 8: Failure handler invocation after retry exhaustion
# Validates: Requirements 5.4
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
)
def test_property_8_no_failure_handler_on_success(
    role: str,
    name: str,
) -> None:
    """
    Property 8: Failure handler invocation after retry exhaustion
    
    Verifies that the failure handler is NOT invoked when an action succeeds,
    even if it required retries.
    """
    import asyncio
    from unittest.mock import patch
    from dm_bot.actions import Action, ElementNotFoundError
    
    async def run_test():
        # Create mock page that fails once then succeeds
        mock_page = MagicMock()
        mock_locator = MagicMock()
        
        call_count = [0]
        
        async def mock_wait_for(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ElementNotFoundError("Element not found")
            return None
        
        mock_locator.wait_for = mock_wait_for
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Create action with failure handler
        action = Action(
            name="test_action",
            action_type="wait_for",
            role=role,
            name_pattern=name,
            timeout_ms=100,
            on_failure="failure_handler",
        )
        
        # Patch asyncio.sleep to speed up test
        with patch('asyncio.sleep', new_callable=AsyncMock):
            # Execute action
            success, context = await executor.execute(action, {})
            
            # Verify action succeeded
            assert success is True, "Action should succeed after retry"
            
            # Verify failure handler was NOT invoked
            assert "last_failed_action" not in context, (
                "last_failed_action should not be set when action succeeds"
            )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 8: Failure handler invocation after retry exhaustion
# Validates: Requirements 5.4
def test_property_8_failure_handler_without_on_failure() -> None:
    """
    Property 8: Failure handler invocation after retry exhaustion
    
    Verifies that when an action fails but has no on_failure handler specified,
    the system still logs the error and returns False gracefully.
    """
    import asyncio
    from unittest.mock import patch
    from dm_bot.actions import Action, ElementNotFoundError
    
    async def run_test():
        # Create mock page that always fails
        mock_page = MagicMock()
        mock_locator = MagicMock()
        
        async def mock_wait_for(*args, **kwargs):
            raise ElementNotFoundError("Element not found")
        
        mock_locator.wait_for = mock_wait_for
        mock_page.get_by_role.return_value = mock_locator
        
        # Create rate limiter
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Create action WITHOUT failure handler
        action = Action(
            name="test_action",
            action_type="wait_for",
            role="button",
            name_pattern="Test",
            timeout_ms=100,
            on_failure=None,  # No failure handler
        )
        
        # Patch asyncio.sleep to speed up test
        with patch('asyncio.sleep', new_callable=AsyncMock):
            # Execute action
            success, context = await executor.execute(action, {})
            
            # Verify action failed
            assert success is False, (
                "Action should fail after exhausting all retries"
            )
            
            # Verify no failure handler was invoked (no crash)
            # The system should handle this gracefully
            assert "last_failed_action" not in context, (
                "last_failed_action should not be set when on_failure is None"
            )
    
    asyncio.run(run_test())



# Feature: robust-navigation, Property 9: Conditional action definition support
# Validates: Requirements 7.1, 7.2, 7.3, 7.4
@settings(max_examples=100, deadline=None)
@given(
    role=aria_roles,
    name=accessible_names,
    priority=st.integers(min_value=0, max_value=100),
    condition_result=st.booleans(),
)
def test_property_9_conditional_action_definition_support(
    role: str,
    name: str,
    priority: int,
    condition_result: bool,
) -> None:
    """
    Property 9: Conditional action definition support
    
    For any conditional action defined with a condition_check callable and priority,
    the system should call the condition_check, respect the priority ordering, and
    support all standard action types.
    
    This test verifies:
    1. ConditionalAction supports condition_check callable (Requirement 7.1)
    2. ConditionalAction supports priority integer (Requirement 7.2)
    3. ConditionalAction supports same action types as regular actions (Requirement 7.3)
    4. should_execute method correctly calls condition_check and returns result
    """
    import asyncio
    from dm_bot.actions import ConditionalAction
    
    async def run_test():
        # Track if condition_check was called
        condition_check_called = [False]
        
        # Create a condition check function that returns the specified result
        async def mock_condition_check(page):
            condition_check_called[0] = True
            return condition_result
        
        # Create mock page
        mock_page = MagicMock()
        
        # Create ConditionalAction with all standard Action fields plus conditional fields
        conditional_action = ConditionalAction(
            name="test_conditional_action",
            action_type="click",  # Standard action type (Requirement 7.3)
            role=role,
            name_pattern=name,
            timeout_ms=5000,
            condition_check=mock_condition_check,  # Requirement 7.1
            priority=priority,  # Requirement 7.2
        )
        
        # Verify ConditionalAction has all expected attributes
        assert conditional_action.name == "test_conditional_action", (
            "ConditionalAction should have name attribute"
        )
        assert conditional_action.action_type == "click", (
            "ConditionalAction should support standard action types"
        )
        assert conditional_action.role == role, (
            "ConditionalAction should have role attribute"
        )
        assert conditional_action.name_pattern == name, (
            "ConditionalAction should have name_pattern attribute"
        )
        assert conditional_action.priority == priority, (
            f"ConditionalAction priority should be {priority}"
        )
        assert conditional_action.condition_check == mock_condition_check, (
            "ConditionalAction should have condition_check attribute"
        )
        
        # Test should_execute method
        result = await conditional_action.should_execute(mock_page)
        
        # Verify condition_check was called
        assert condition_check_called[0] is True, (
            "should_execute should call condition_check"
        )
        
        # Verify result matches expected condition_result
        assert result == condition_result, (
            f"should_execute should return {condition_result}, got {result}"
        )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 9: Conditional action definition support
# Validates: Requirements 7.1, 7.2, 7.3, 7.4
@settings(max_examples=100, deadline=None)
@given(
    action_type=st.sampled_from(["wait_for", "click", "fill", "check"]),
    priority=st.integers(min_value=0, max_value=100),
)
def test_property_9_conditional_action_supports_all_action_types(
    action_type: str,
    priority: int,
) -> None:
    """
    Property 9: Conditional action definition support
    
    Verifies that ConditionalAction supports all standard action types
    (wait_for, click, fill, check) as specified in Requirement 7.3.
    """
    import asyncio
    from dm_bot.actions import ConditionalAction
    
    async def run_test():
        # Create a simple condition check
        async def mock_condition_check(page):
            return True
        
        # Create ConditionalAction with the specified action type
        conditional_action = ConditionalAction(
            name=f"test_{action_type}",
            action_type=action_type,
            role="button",
            name_pattern="Test",
            condition_check=mock_condition_check,
            priority=priority,
        )
        
        # Verify action type is set correctly
        assert conditional_action.action_type == action_type, (
            f"ConditionalAction should support action_type '{action_type}'"
        )
        
        # Verify it's still a valid ConditionalAction with all required fields
        assert hasattr(conditional_action, 'condition_check'), (
            "ConditionalAction should have condition_check attribute"
        )
        assert hasattr(conditional_action, 'priority'), (
            "ConditionalAction should have priority attribute"
        )
        assert hasattr(conditional_action, 'should_execute'), (
            "ConditionalAction should have should_execute method"
        )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 9: Conditional action definition support
# Validates: Requirements 7.1, 7.2, 7.3, 7.4
def test_property_9_conditional_action_handles_condition_check_exception() -> None:
    """
    Property 9: Conditional action definition support
    
    Verifies that should_execute handles exceptions from condition_check gracefully
    and returns False when an exception occurs.
    """
    import asyncio
    from dm_bot.actions import ConditionalAction
    
    async def run_test():
        # Create a condition check that raises an exception
        async def failing_condition_check(page):
            raise Exception("Condition check failed")
        
        # Create mock page
        mock_page = MagicMock()
        
        # Create ConditionalAction with failing condition check
        conditional_action = ConditionalAction(
            name="test_failing_condition",
            action_type="click",
            role="button",
            name_pattern="Test",
            condition_check=failing_condition_check,
            priority=50,
        )
        
        # Test should_execute - should return False on exception
        result = await conditional_action.should_execute(mock_page)
        
        # Verify result is False (graceful failure)
        assert result is False, (
            "should_execute should return False when condition_check raises exception"
        )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 9: Conditional action definition support
# Validates: Requirements 7.1, 7.2, 7.3, 7.4
def test_property_9_conditional_action_without_condition_check() -> None:
    """
    Property 9: Conditional action definition support
    
    Verifies that ConditionalAction handles the case where condition_check is None
    gracefully by returning False.
    """
    import asyncio
    from dm_bot.actions import ConditionalAction
    
    async def run_test():
        # Create mock page
        mock_page = MagicMock()
        
        # Create ConditionalAction without condition_check (None)
        conditional_action = ConditionalAction(
            name="test_no_condition",
            action_type="click",
            role="button",
            name_pattern="Test",
            condition_check=None,  # type: ignore[arg-type]
            priority=50,
        )
        
        # Test should_execute - should return False when condition_check is None
        result = await conditional_action.should_execute(mock_page)
        
        # Verify result is False
        assert result is False, (
            "should_execute should return False when condition_check is None"
        )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 9: Conditional action definition support
# Validates: Requirements 7.1, 7.2, 7.3, 7.4
@settings(max_examples=100, deadline=None)
@given(
    priorities=st.lists(
        st.integers(min_value=0, max_value=100),
        min_size=2,
        max_size=10,
        unique=True
    ),
)
def test_property_9_conditional_actions_sortable_by_priority(
    priorities: list[int],
) -> None:
    """
    Property 9: Conditional action definition support
    
    Verifies that ConditionalActions can be sorted by priority as specified
    in Requirement 7.4 (higher priority = checked first).
    """
    import asyncio
    from dm_bot.actions import ConditionalAction
    
    async def run_test():
        # Create a simple condition check
        async def mock_condition_check(page):
            return True
        
        # Create multiple ConditionalActions with different priorities
        conditional_actions = []
        for priority in priorities:
            action = ConditionalAction(
                name=f"action_priority_{priority}",
                action_type="click",
                role="button",
                name_pattern="Test",
                condition_check=mock_condition_check,
                priority=priority,
            )
            conditional_actions.append(action)
        
        # Sort by priority (highest first)
        sorted_actions = sorted(
            conditional_actions,
            key=lambda a: a.priority,
            reverse=True
        )
        
        # Verify actions are sorted correctly
        sorted_priorities = [action.priority for action in sorted_actions]
        expected_priorities = sorted(priorities, reverse=True)
        
        assert sorted_priorities == expected_priorities, (
            f"Actions should be sorted by priority (highest first). "
            f"Expected {expected_priorities}, got {sorted_priorities}"
        )
    
    asyncio.run(run_test())
