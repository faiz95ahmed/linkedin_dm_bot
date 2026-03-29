"""Property-based tests for NotificationService.

Feature: linkedin-navigation
"""

import subprocess
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings

from dm_bot.notifications import NotificationService


# Feature: linkedin-navigation, Property 12: Notification delivery on critical events
# Validates: Requirements 6.1, 6.2, 6.3, 6.5
@settings(max_examples=100, deadline=None)
@given(
    title=st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126, blacklist_characters='"')),
    message=st.text(min_size=1, max_size=200, alphabet=st.characters(min_codepoint=32, max_codepoint=126, blacklist_characters='"')),
)
def test_property_12_notification_delivery(title: str, message: str) -> None:
    """
    Property 12: Notification delivery on critical events
    
    For any critical event (checkpoint detection, fatal error), the system
    should send a macOS notification using osascript with appropriate title
    and message content including event details.
    
    This test verifies that notify() calls osascript with correct parameters.
    """
    service = NotificationService()
    
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr='', stdout='')
        
        service.notify(title, message)
        
        # Verify osascript was called
        assert mock_run.called, "osascript subprocess.run was not called"
        
        # Verify the command structure
        call_args = mock_run.call_args
        args = call_args[0][0]  # First positional argument
        
        assert args[0] == "osascript", f"Expected 'osascript', got '{args[0]}'"
        assert args[1] == "-e", f"Expected '-e' flag, got '{args[1]}'"
        
        # Verify the script contains title and message
        script = args[2]
        assert "display notification" in script, "Script missing 'display notification'"
        assert message in script, f"Message '{message}' not in script"
        assert title in script, f"Title '{title}' not in script"


# Feature: linkedin-navigation, Property 12: Notification delivery on critical events
# Validates: Requirements 6.1, 6.2, 6.3, 6.5
@settings(max_examples=100, deadline=None)
@given(
    url=st.text(min_size=10, max_size=100, alphabet=st.characters(min_codepoint=32, max_codepoint=126, blacklist_characters='"')),
)
def test_property_12_checkpoint_notification_format(url: str) -> None:
    """
    Property 12: Notification delivery on critical events
    
    For checkpoint detection events, the system should send a notification
    with title "LinkedIn Bot" and message containing the checkpoint URL.
    """
    service = NotificationService()
    
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr='', stdout='')
        
        service.notify_checkpoint(url)
        
        # Verify osascript was called
        assert mock_run.called, "osascript subprocess.run was not called"
        
        # Verify the script contains expected content
        call_args = mock_run.call_args
        script = call_args[0][0][2]  # args[2] is the script
        
        assert "LinkedIn Bot" in script, "Title 'LinkedIn Bot' not in script"
        assert url in script, f"URL '{url}' not in checkpoint notification"
        assert "checkpoint" in script.lower(), "Word 'checkpoint' not in notification"


# Feature: linkedin-navigation, Property 12: Notification delivery on critical events
# Validates: Requirements 6.1, 6.2, 6.3, 6.5
@settings(max_examples=100, deadline=None)
@given(
    error_message=st.text(min_size=1, max_size=100, alphabet=st.characters(min_codepoint=32, max_codepoint=126, blacklist_characters='"')),
)
def test_property_12_error_notification_format(error_message: str) -> None:
    """
    Property 12: Notification delivery on critical events
    
    For error events, the system should send a notification with title
    "LinkedIn Bot" and message containing the error type and details.
    """
    service = NotificationService()
    
    # Create a test exception
    error = ValueError(error_message)
    
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr='', stdout='')
        
        service.notify_error(error)
        
        # Verify osascript was called
        assert mock_run.called, "osascript subprocess.run was not called"
        
        # Verify the script contains expected content
        call_args = mock_run.call_args
        script = call_args[0][0][2]  # args[2] is the script
        
        assert "LinkedIn Bot" in script, "Title 'LinkedIn Bot' not in script"
        assert "ValueError" in script, "Error type 'ValueError' not in notification"
        assert error_message in script, f"Error message '{error_message}' not in notification"


# Feature: linkedin-navigation, Property 13: Notification failure resilience
# Validates: Requirements 6.4
@settings(max_examples=100, deadline=None)
@given(
    title=st.text(min_size=1, max_size=50, alphabet=st.characters(min_codepoint=32, max_codepoint=126, blacklist_characters='"')),
    message=st.text(min_size=1, max_size=200, alphabet=st.characters(min_codepoint=32, max_codepoint=126, blacklist_characters='"')),
)
def test_property_13_notification_failure_resilience(title: str, message: str) -> None:
    """
    Property 13: Notification failure resilience
    
    For any notification command failure, the system should log the failure
    but continue execution without throwing an exception.
    
    This test verifies that notify() handles subprocess failures gracefully.
    """
    service = NotificationService()
    
    # Test CalledProcessError (command fails)
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["osascript"],
            stderr="Command failed"
        )
        
        # Should not raise exception
        try:
            service.notify(title, message)
        except Exception as e:
            raise AssertionError(
                f"notify() raised exception on subprocess failure: {e}"
            )
    
    # Test TimeoutExpired
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["osascript"],
            timeout=5.0
        )
        
        # Should not raise exception
        try:
            service.notify(title, message)
        except Exception as e:
            raise AssertionError(
                f"notify() raised exception on timeout: {e}"
            )
    
    # Test generic Exception
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = RuntimeError("Unexpected error")
        
        # Should not raise exception
        try:
            service.notify(title, message)
        except Exception as e:
            raise AssertionError(
                f"notify() raised exception on generic error: {e}"
            )
