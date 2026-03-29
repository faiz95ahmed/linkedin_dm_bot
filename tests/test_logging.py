"""Property-based tests for logging system.

Feature: linkedin-navigation
"""

import asyncio
import logging
import re
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st

from dm_bot.actions import Action, ActionExecutor, ElementNotFoundError
from dm_bot.config import RateLimiter, setup_logging, LOG_DATE_FORMAT
from dm_bot.navigation import NavigationEngine
from dm_bot.notifications import NotificationService


# Helper function to capture log output
class LogCapture:
    """Captures log output for testing."""
    
    def __init__(self):
        self.handler = logging.StreamHandler(StringIO())
        self.handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt=LOG_DATE_FORMAT,
        )
        self.handler.setFormatter(formatter)
    
    def __enter__(self):
        # Add handler to root logger
        logging.getLogger().addHandler(self.handler)
        return self
    
    def __exit__(self, *args):
        # Remove handler
        logging.getLogger().removeHandler(self.handler)
    
    def get_output(self) -> str:
        """Get captured log output."""
        return self.handler.stream.getvalue()
    
    def get_lines(self) -> list[str]:
        """Get captured log output as lines."""
        return self.get_output().strip().split('\n')


# Feature: linkedin-navigation, Property 14: Comprehensive action logging
# Validates: Requirements 8.1, 8.2, 8.3
@settings(max_examples=100, deadline=None)
@given(
    action_name=st.text(min_size=1, max_size=50, alphabet=st.characters(
        min_codepoint=32, max_codepoint=126, blacklist_characters='\n\r'
    )),
    action_type=st.sampled_from(['wait_for', 'click', 'fill', 'check']),
    should_succeed=st.booleans(),
)
def test_property_14_action_logging_info_on_success(
    action_name: str,
    action_type: str,
    should_succeed: bool,
) -> None:
    """
    Property 14: Comprehensive action logging
    
    For any action execution, the system should log at the appropriate level
    (INFO for success, WARNING for retries, ERROR for critical failures)
    with action details.
    
    This test verifies that successful actions are logged at INFO level
    with action name and type.
    """
    async def run_test():
        # Setup logging
        setup_logging(log_level="INFO", log_file=None)
        
        # Create mock page and rate limiter
        mock_page = AsyncMock()
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create action
        action = Action(
            name=action_name,
            action_type=action_type,
            role="button",
            name_pattern="Test",
        )
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Mock the handler methods to control success/failure
        if should_succeed:
            executor._handle_wait_for = AsyncMock(return_value=True)
            executor._handle_click = AsyncMock(return_value=True)
            executor._handle_fill = AsyncMock(return_value=True)
            executor._handle_check = AsyncMock(return_value=True)
        else:
            executor._handle_wait_for = AsyncMock(return_value=False)
            executor._handle_click = AsyncMock(return_value=False)
            executor._handle_fill = AsyncMock(return_value=False)
            executor._handle_check = AsyncMock(return_value=False)
        
        # Capture logs
        with LogCapture() as log_capture:
            # Patch asyncio.sleep to avoid delays
            with patch('asyncio.sleep', new_callable=AsyncMock):
                # Execute action
                success, context = await executor.execute(action, {})
            
            # Get log output
            log_output = log_capture.get_output()
            
            # Verify logging occurred
            assert len(log_output) > 0, "No log output captured"
            
            # Verify action name and type are logged (Requirement 8.1)
            assert action_name in log_output, (
                f"Action name '{action_name}' not found in logs"
            )
            assert action_type in log_output, (
                f"Action type '{action_type}' not found in logs"
            )
            
            # Verify appropriate log level
            if should_succeed:
                # Should have INFO level logs for success
                assert "INFO" in log_output, "INFO level not found for successful action"
                assert "succeeded" in log_output.lower() or "executing" in log_output.lower(), (
                    "Success indicator not found in logs"
                )
            else:
                # Should have WARNING or ERROR level logs for failure
                assert "WARNING" in log_output or "ERROR" in log_output, (
                    "WARNING or ERROR level not found for failed action"
                )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 14: Comprehensive action logging
# Validates: Requirements 8.1, 8.2, 8.3
@settings(max_examples=50, deadline=None)
@given(
    action_name=st.text(min_size=1, max_size=30, alphabet=st.characters(
        min_codepoint=32, max_codepoint=126, blacklist_characters='\n\r'
    )),
)
def test_property_14_action_logging_warning_on_retry(action_name: str) -> None:
    """
    Property 14: Comprehensive action logging
    
    For any action that fails and triggers a retry, the system should log
    at WARNING level with the retry attempt number.
    """
    async def run_test():
        # Setup logging
        setup_logging(log_level="DEBUG", log_file=None)
        
        # Create mock page and rate limiter
        mock_page = AsyncMock()
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create action that will fail
        action = Action(
            name=action_name,
            action_type="click",
            role="button",
            name_pattern="NonExistent",
        )
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Mock to raise ElementNotFoundError on first attempts, then succeed
        call_count = 0
        async def mock_click(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ElementNotFoundError("Element not found")
            return True
        
        executor.click_element = mock_click
        
        # Capture logs
        with LogCapture() as log_capture:
            # Patch asyncio.sleep to avoid delays
            with patch('asyncio.sleep', new_callable=AsyncMock):
                # Execute action (will retry once)
                success, context = await executor.execute(action, {})
            
            # Get log output
            log_output = log_capture.get_output()
            
            # Verify WARNING level logging for retry (Requirement 8.2)
            assert "WARNING" in log_output, "WARNING level not found for retry"
            
            # Verify retry attempt number is logged (Requirement 8.2)
            assert "attempt" in log_output.lower(), (
                "Retry attempt number not found in logs"
            )
            
            # Verify action name is in logs
            assert action_name in log_output, (
                f"Action name '{action_name}' not found in retry logs"
            )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 14: Comprehensive action logging
# Validates: Requirements 8.1, 8.2, 8.3
def test_property_14_checkpoint_logging_error_level() -> None:
    """
    Property 14: Comprehensive action logging
    
    For checkpoint detection, the system should log at ERROR level
    with the current URL.
    """
    async def run_test():
        # Setup logging
        setup_logging(log_level="INFO", log_file=None)
        
        # Create mock page with checkpoint URL
        mock_page = AsyncMock()
        mock_page.url = "https://www.linkedin.com/checkpoint/challenge/verify"
        
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        notifier = NotificationService()
        
        # Create navigation engine
        engine = NavigationEngine(
            page=mock_page,
            rate_limiter=rate_limiter,
            notifier=notifier,
        )
        
        # Capture logs
        with LogCapture() as log_capture:
            # Check for checkpoint
            is_checkpoint = await engine.check_for_checkpoint()
            
            # Get log output
            log_output = log_capture.get_output()
            
            # Verify checkpoint was detected
            assert is_checkpoint, "Checkpoint should be detected"
            
            # Verify ERROR level logging (Requirement 8.3)
            assert "ERROR" in log_output, "ERROR level not found for checkpoint"
            
            # Verify URL is logged (Requirement 8.3)
            assert "checkpoint" in log_output.lower(), (
                "Checkpoint URL pattern not found in logs"
            )
            assert mock_page.url in log_output or "checkpoint/challenge" in log_output, (
                "URL not found in checkpoint logs"
            )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 14: Comprehensive action logging
# Validates: Requirements 8.1, 8.2, 8.3
@settings(max_examples=50, deadline=None)
@given(
    action_name=st.text(min_size=1, max_size=30, alphabet=st.characters(
        min_codepoint=32, max_codepoint=126, blacklist_characters='\n\r'
    )),
)
def test_property_14_action_logging_error_on_exhaustion(action_name: str) -> None:
    """
    Property 14: Comprehensive action logging
    
    For any action that exhausts all retry attempts, the system should log
    at ERROR level with failure details.
    """
    async def run_test():
        # Setup logging
        setup_logging(log_level="DEBUG", log_file=None)
        
        # Create mock page and rate limiter
        mock_page = AsyncMock()
        rate_limiter = RateLimiter(delay_range=(0.0, 0.0))
        
        # Create action that will always fail
        action = Action(
            name=action_name,
            action_type="click",
            role="button",
            name_pattern="NonExistent",
        )
        
        # Create executor
        executor = ActionExecutor(page=mock_page, rate_limiter=rate_limiter)
        
        # Mock to always fail
        executor.click_element = AsyncMock(return_value=False)
        
        # Capture logs
        with LogCapture() as log_capture:
            # Patch asyncio.sleep to avoid delays
            with patch('asyncio.sleep', new_callable=AsyncMock):
                # Execute action (will fail all retries)
                success, context = await executor.execute(action, {})
            
            # Get log output
            log_output = log_capture.get_output()
            
            # Verify action failed
            assert not success, "Action should have failed"
            
            # Verify ERROR level logging for exhaustion (Requirement 8.2)
            assert "ERROR" in log_output, "ERROR level not found for retry exhaustion"
            
            # Verify failure details are logged
            assert action_name in log_output, (
                f"Action name '{action_name}' not found in failure logs"
            )
            assert "failed" in log_output.lower() or "exhausted" in log_output.lower(), (
                "Failure indicator not found in logs"
            )
    
    asyncio.run(run_test())



# Feature: linkedin-navigation, Property 15: Timestamp format consistency
# Validates: Requirements 8.5
@settings(max_examples=100, deadline=None)
@given(
    log_message=st.text(min_size=1, max_size=100, alphabet=st.characters(
        min_codepoint=32, max_codepoint=126, blacklist_characters='\n\r'
    )),
)
def test_property_15_timestamp_format_consistency(log_message: str) -> None:
    """
    Property 15: Timestamp format consistency
    
    For any log entry, the timestamp should match the format "YYYY-MM-DD HH:MM:SS".
    
    This test verifies that all log entries have timestamps in the correct format.
    """
    async def run_test():
        # Setup logging with specific format
        setup_logging(log_level="INFO", log_file=None)
        
        # Get a logger
        logger = logging.getLogger("test_logger")
        
        # Capture logs
        with LogCapture() as log_capture:
            # Log a message
            logger.info(log_message)
            
            # Get log output
            log_output = log_capture.get_output()
            
            # Verify log was captured
            assert len(log_output) > 0, "No log output captured"
            
            # Extract timestamp from log line
            # Format: "YYYY-MM-DD HH:MM:SS - logger_name - LEVEL - message"
            lines = log_capture.get_lines()
            
            for line in lines:
                if not line.strip():
                    continue
                
                # Timestamp should be at the beginning of the line
                # Pattern: YYYY-MM-DD HH:MM:SS
                timestamp_pattern = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'
                
                match = re.match(timestamp_pattern, line)
                assert match is not None, (
                    f"Timestamp format 'YYYY-MM-DD HH:MM:SS' not found at start of log line: {line}"
                )
                
                # Verify the timestamp is valid
                timestamp_str = match.group(0)
                
                # Check format components
                date_part, time_part = timestamp_str.split(' ')
                year, month, day = date_part.split('-')
                hour, minute, second = time_part.split(':')
                
                # Verify ranges
                assert 1900 <= int(year) <= 2100, f"Invalid year: {year}"
                assert 1 <= int(month) <= 12, f"Invalid month: {month}"
                assert 1 <= int(day) <= 31, f"Invalid day: {day}"
                assert 0 <= int(hour) <= 23, f"Invalid hour: {hour}"
                assert 0 <= int(minute) <= 59, f"Invalid minute: {minute}"
                assert 0 <= int(second) <= 59, f"Invalid second: {second}"
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 15: Timestamp format consistency
# Validates: Requirements 8.5
def test_property_15_timestamp_format_in_all_log_levels() -> None:
    """
    Property 15: Timestamp format consistency
    
    For any log level (DEBUG, INFO, WARNING, ERROR, CRITICAL), the timestamp
    format should be consistent: "YYYY-MM-DD HH:MM:SS".
    """
    async def run_test():
        # Setup logging
        setup_logging(log_level="DEBUG", log_file=None)
        
        # Get a logger
        logger = logging.getLogger("test_logger")
        
        # Test all log levels
        log_levels = [
            (logging.DEBUG, "debug message"),
            (logging.INFO, "info message"),
            (logging.WARNING, "warning message"),
            (logging.ERROR, "error message"),
            (logging.CRITICAL, "critical message"),
        ]
        
        # Timestamp pattern
        timestamp_pattern = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'
        
        for level, message in log_levels:
            # Capture logs
            with LogCapture() as log_capture:
                # Log at specific level
                logger.log(level, message)
                
                # Get log output
                log_output = log_capture.get_output()
                
                # Verify log was captured
                assert len(log_output) > 0, f"No log output for level {level}"
                
                # Verify timestamp format
                lines = log_capture.get_lines()
                for line in lines:
                    if not line.strip():
                        continue
                    
                    match = re.match(timestamp_pattern, line)
                    assert match is not None, (
                        f"Timestamp format not found in {logging.getLevelName(level)} log: {line}"
                    )
    
    asyncio.run(run_test())


# Feature: linkedin-navigation, Property 15: Timestamp format consistency
# Validates: Requirements 8.5
def test_property_15_timestamp_format_in_file_logs() -> None:
    """
    Property 15: Timestamp format consistency
    
    For file logs, the timestamp format should also be "YYYY-MM-DD HH:MM:SS".
    """
    import tempfile
    import os
    
    async def run_test():
        # Create temporary log file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            log_file_path = f.name
        
        try:
            # Setup logging with file handler
            setup_logging(log_level="INFO", log_file=log_file_path)
            
            # Get a logger
            logger = logging.getLogger("test_file_logger")
            
            # Log some messages
            logger.info("Test message 1")
            logger.warning("Test message 2")
            logger.error("Test message 3")
            
            # Force flush
            for handler in logging.getLogger().handlers:
                handler.flush()
            
            # Read log file
            with open(log_file_path, 'r') as f:
                log_content = f.read()
            
            # Verify log file has content
            assert len(log_content) > 0, "Log file is empty"
            
            # Verify timestamp format in each line
            timestamp_pattern = r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'
            
            lines = log_content.strip().split('\n')
            for line in lines:
                if not line.strip() or line.startswith('='):
                    # Skip empty lines and separator lines
                    continue
                
                match = re.match(timestamp_pattern, line)
                assert match is not None, (
                    f"Timestamp format not found in file log line: {line}"
                )
        
        finally:
            # Clean up temp file
            if os.path.exists(log_file_path):
                os.remove(log_file_path)
    
    asyncio.run(run_test())
