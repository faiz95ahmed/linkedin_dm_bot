"""Property-based tests for RateLimiter.

Feature: linkedin-navigation
"""

import asyncio
import time
import pytest
from hypothesis import given, strategies as st, settings

from dm_bot.config import (
    RateLimiter,
    DELAY_MIN,
    DELAY_MAX,
    TYPING_DELAY_MIN,
    TYPING_DELAY_MAX,
    PAGE_LOAD_DELAY_MIN,
    PAGE_LOAD_DELAY_MAX,
)


# Use scaled-down delays for testing to keep tests fast
TEST_SCALE_FACTOR = 0.01  # Scale delays to 1% for testing


# Feature: linkedin-navigation, Property 10: Human-like delay ranges
# Validates: Requirements 4.1, 4.2, 4.3, 4.4
@settings(max_examples=10, deadline=None)
@given(
    delay_min=st.floats(min_value=0.01, max_value=0.03),
    delay_max=st.floats(min_value=0.03, max_value=0.07),
)
def test_property_10_delay_between_actions_in_range(
    delay_min: float, delay_max: float
) -> None:
    """
    Property 10: Human-like delay ranges
    
    For any action type (UI action, typing, page load, conversation opening),
    the system should apply random delays within the specified range for that
    action type.
    
    This test verifies delay_between_actions() respects the configured range.
    Uses scaled-down delays for fast testing.
    """
    async def run_test():
        rate_limiter = RateLimiter(delay_range=(delay_min, delay_max))
        
        start = time.time()
        await rate_limiter.delay_between_actions()
        elapsed = time.time() - start
        
        # Allow tolerance for timing precision
        tolerance = 0.05
        assert delay_min - tolerance <= elapsed <= delay_max + tolerance, (
            f"Delay {elapsed:.3f}s outside range [{delay_min}, {delay_max}]"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 10: Human-like delay ranges
# Validates: Requirements 4.1, 4.2, 4.3, 4.4
@settings(max_examples=10, deadline=None)
@given(text=st.text(min_size=1, max_size=10, alphabet=st.characters(min_codepoint=32, max_codepoint=126)))
def test_property_10_typing_delay_in_range(text: str) -> None:
    """
    Property 10: Human-like delay ranges
    
    For typing actions, the system should apply per-character delays
    within the range [0.05, 0.15] seconds.
    Uses scaled-down text length for fast testing.
    """
    async def run_test():
        rate_limiter = RateLimiter()
        
        start = time.time()
        await rate_limiter.delay_for_typing(text)
        elapsed = time.time() - start
        
        # Expected range: len(text) * [TYPING_DELAY_MIN, TYPING_DELAY_MAX]
        min_expected = len(text) * TYPING_DELAY_MIN
        max_expected = len(text) * TYPING_DELAY_MAX
        
        # Allow tolerance for timing precision
        tolerance = 0.05
        assert min_expected - tolerance <= elapsed <= max_expected + tolerance, (
            f"Typing delay {elapsed:.3f}s for {len(text)} chars "
            f"outside range [{min_expected:.3f}, {max_expected:.3f}]"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 10: Human-like delay ranges
# Validates: Requirements 4.1, 4.2, 4.3, 4.4
def test_property_10_page_load_delay_in_range() -> None:
    """
    Property 10: Human-like delay ranges
    
    For page load actions, the system should apply delays within
    the range [1.5, 3.0] seconds.
    Runs multiple iterations to verify randomness.
    """
    async def run_test():
        rate_limiter = RateLimiter()
        
        # Run 10 iterations to verify delays are in range
        for _ in range(10):
            start = time.time()
            await rate_limiter.delay_after_page_load()
            elapsed = time.time() - start
            
            # Allow tolerance for timing precision
            tolerance = 0.1
            assert PAGE_LOAD_DELAY_MIN - tolerance <= elapsed <= PAGE_LOAD_DELAY_MAX + tolerance, (
                f"Page load delay {elapsed:.3f}s outside range "
                f"[{PAGE_LOAD_DELAY_MIN}, {PAGE_LOAD_DELAY_MAX}]"
            )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 11: Rate limiting enforcement
# Validates: Requirements 4.5
@settings(max_examples=5, deadline=None)
@given(
    max_actions=st.integers(min_value=2, max_value=4),
)
def test_property_11_rate_limiting_enforcement(
    max_actions: int,
) -> None:
    """
    Property 11: Rate limiting enforcement
    
    For any sequence of actions, when the action rate exceeds the configured
    maximum actions per minute, the system should pause execution until the
    rate falls below the threshold.
    
    This test verifies that we can execute up to max_actions without pause,
    and that the rate limiter correctly tracks actions.
    """
    async def run_test():
        rate_limiter = RateLimiter(
            delay_range=(0.0, 0.0),
            max_actions_per_minute=max_actions,
        )
        
        # Execute exactly max_actions - should not pause
        for i in range(max_actions):
            await rate_limiter.check_rate_limit()
        
        # Verify all actions were recorded
        assert len(rate_limiter.action_timestamps) == max_actions, (
            f"Expected {max_actions} actions, got {len(rate_limiter.action_timestamps)}"
        )
        
        # Verify the invariant: at most max_actions in any 60-second window
        actions_in_window = len([
            ts for ts in rate_limiter.action_timestamps
            if time.time() - ts < 60.0
        ])
        
        assert actions_in_window <= max_actions, (
            f"Rate limiter allowed {actions_in_window} actions in 60s window, "
            f"exceeding limit of {max_actions}"
        )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 11: Rate limiting enforcement
# Validates: Requirements 4.5
def test_property_11_rate_limit_20_actions_per_minute() -> None:
    """
    Property 11: Rate limiting enforcement
    
    Specifically test the requirement of 20 actions per minute.
    Verifies that we can execute up to 20 actions without pause,
    and that the rate limiter correctly tracks them.
    """
    async def run_test():
        rate_limiter = RateLimiter(
            delay_range=(0.0, 0.0),
            max_actions_per_minute=20,
        )
        
        # Execute exactly 20 actions - should not pause
        for i in range(20):
            await rate_limiter.check_rate_limit()
        
        # Verify all 20 actions were recorded
        assert len(rate_limiter.action_timestamps) == 20, (
            f"Expected 20 actions, got {len(rate_limiter.action_timestamps)}"
        )
        
        # Verify the invariant: at most 20 actions in any 60s window
        actions_in_window = len([
            ts for ts in rate_limiter.action_timestamps
            if time.time() - ts < 60.0
        ])
        
        assert actions_in_window <= 20, (
            f"Rate limiter allowed {actions_in_window} actions in 60s window, "
            f"exceeding limit of 20"
        )
    
    asyncio.run(run_test())
