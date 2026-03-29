"""
Tests for action flow definitions.

This module tests that the predefined action flows (LOGIN_FLOW,
NAVIGATE_TO_MESSAGING_FLOW, CHECK_LOGIN_STATE) are correctly defined
and meet the requirements.

Requirements: 1.4, 1.5, 1.6, 3.1, 3.3, 3.4
"""

import pytest
from dm_bot.actions import (
    LOGIN_FLOW,
    NAVIGATE_TO_MESSAGING_FLOW,
    CHECK_LOGIN_STATE,
    Action,
    check_login_state_handler,
)


class TestLoginFlow:
    """Test LOGIN_FLOW action definitions (Requirements 1.4, 1.5, 1.6)."""
    
    def test_login_flow_exists(self):
        """LOGIN_FLOW should be defined and non-empty."""
        assert LOGIN_FLOW is not None
        assert len(LOGIN_FLOW) > 0
    
    def test_login_flow_has_email_field_action(self):
        """LOGIN_FLOW should include action for email field (Requirement 1.4)."""
        # Find actions that interact with email field
        email_actions = [
            action for action in LOGIN_FLOW
            if action.role == "textbox" and "Email or phone" in action.name_pattern
        ]
        assert len(email_actions) >= 1, "Should have at least one email field action"
        
        # Verify at least one is a fill action
        fill_actions = [a for a in email_actions if a.action_type == "fill"]
        assert len(fill_actions) >= 1, "Should have fill action for email field"
    
    def test_login_flow_has_password_field_action(self):
        """LOGIN_FLOW should include action for password field (Requirement 1.5)."""
        # Find actions that interact with password field
        password_actions = [
            action for action in LOGIN_FLOW
            if action.role == "textbox" and "Password" in action.name_pattern
        ]
        assert len(password_actions) >= 1, "Should have at least one password field action"
        
        # Verify at least one is a fill action
        fill_actions = [a for a in password_actions if a.action_type == "fill"]
        assert len(fill_actions) >= 1, "Should have fill action for password field"
    
    def test_login_flow_has_sign_in_button_action(self):
        """LOGIN_FLOW should include action for sign-in button (Requirement 1.6)."""
        # Find actions that interact with sign-in button
        signin_actions = [
            action for action in LOGIN_FLOW
            if action.role == "button" and "Sign in" in action.name_pattern
        ]
        assert len(signin_actions) >= 1, "Should have at least one sign-in button action"
        
        # Verify at least one is a click action
        click_actions = [a for a in signin_actions if a.action_type == "click"]
        assert len(click_actions) >= 1, "Should have click action for sign-in button"
    
    def test_login_flow_actions_are_action_objects(self):
        """All items in LOGIN_FLOW should be Action objects."""
        for action in LOGIN_FLOW:
            assert isinstance(action, Action)
    
    def test_login_flow_actions_have_names(self):
        """All actions in LOGIN_FLOW should have names."""
        for action in LOGIN_FLOW:
            assert action.name is not None
            assert len(action.name) > 0


class TestNavigateToMessagingFlow:
    """Test NAVIGATE_TO_MESSAGING_FLOW action definitions (Requirements 3.1, 3.3, 3.4)."""
    
    def test_navigate_to_messaging_flow_exists(self):
        """NAVIGATE_TO_MESSAGING_FLOW should be defined and non-empty."""
        assert NAVIGATE_TO_MESSAGING_FLOW is not None
        assert len(NAVIGATE_TO_MESSAGING_FLOW) > 0
    
    def test_navigate_to_messaging_flow_has_messaging_link_action(self):
        """NAVIGATE_TO_MESSAGING_FLOW should include action for messaging link (Requirement 3.1)."""
        # Find actions that interact with messaging link
        messaging_link_actions = [
            action for action in NAVIGATE_TO_MESSAGING_FLOW
            if action.role == "link" and "Messaging" in action.name_pattern
        ]
        assert len(messaging_link_actions) >= 1, "Should have at least one messaging link action"
        
        # Verify at least one is a click action
        click_actions = [a for a in messaging_link_actions if a.action_type == "click"]
        assert len(click_actions) >= 1, "Should have click action for messaging link"
    
    def test_navigate_to_messaging_flow_uses_regex_pattern(self):
        """Messaging link action should use regex pattern (Requirement 3.1)."""
        # Find messaging link actions
        messaging_link_actions = [
            action for action in NAVIGATE_TO_MESSAGING_FLOW
            if action.role == "link" and "Messaging" in action.name_pattern
        ]
        
        # At least one should use regex pattern (contains .* or other regex chars)
        regex_actions = [
            a for a in messaging_link_actions
            if ".*" in a.name_pattern or "+" in a.name_pattern or "?" in a.name_pattern
        ]
        assert len(regex_actions) >= 1, "Should use regex pattern for flexible matching"
    
    def test_navigate_to_messaging_flow_has_conversation_list_action(self):
        """NAVIGATE_TO_MESSAGING_FLOW should include action for conversation list (Requirement 3.3)."""
        # Find actions that interact with list
        list_actions = [
            action for action in NAVIGATE_TO_MESSAGING_FLOW
            if action.role == "list"
        ]
        assert len(list_actions) >= 1, "Should have at least one list action"
        
        # Verify at least one is a wait_for action
        wait_actions = [a for a in list_actions if a.action_type == "wait_for"]
        assert len(wait_actions) >= 1, "Should have wait_for action for conversation list"
    
    def test_navigate_to_messaging_flow_actions_are_action_objects(self):
        """All items in NAVIGATE_TO_MESSAGING_FLOW should be Action objects."""
        for action in NAVIGATE_TO_MESSAGING_FLOW:
            assert isinstance(action, Action)
    
    def test_navigate_to_messaging_flow_actions_have_names(self):
        """All actions in NAVIGATE_TO_MESSAGING_FLOW should have names."""
        for action in NAVIGATE_TO_MESSAGING_FLOW:
            assert action.name is not None
            assert len(action.name) > 0


class TestCheckLoginState:
    """Test CHECK_LOGIN_STATE action definitions (Requirement 2.1)."""
    
    def test_check_login_state_exists(self):
        """CHECK_LOGIN_STATE should be defined and non-empty."""
        assert CHECK_LOGIN_STATE is not None
        assert len(CHECK_LOGIN_STATE) > 0
    
    def test_check_login_state_has_custom_handler(self):
        """CHECK_LOGIN_STATE should use custom handler (Requirement 2.1)."""
        # Find actions with custom handler
        handler_actions = [
            action for action in CHECK_LOGIN_STATE
            if action.handler is not None
        ]
        assert len(handler_actions) >= 1, "Should have at least one action with custom handler"
    
    def test_check_login_state_handler_function_exists(self):
        """check_login_state_handler function should be defined."""
        assert check_login_state_handler is not None
        assert callable(check_login_state_handler)
    
    def test_check_login_state_actions_are_action_objects(self):
        """All items in CHECK_LOGIN_STATE should be Action objects."""
        for action in CHECK_LOGIN_STATE:
            assert isinstance(action, Action)
    
    def test_check_login_state_actions_have_names(self):
        """All actions in CHECK_LOGIN_STATE should have names."""
        for action in CHECK_LOGIN_STATE:
            assert action.name is not None
            assert len(action.name) > 0


class TestCheckLoginStateHandler:
    """Test check_login_state_handler function (Requirement 2.1)."""
    
    def test_handler_returns_true_when_not_logged_in_url(self):
        """Handler should return True when URL does not contain '/login'."""
        # Mock page object
        class MockPage:
            url = "https://www.linkedin.com/feed/"
        
        page = MockPage()
        context = {}
        
        result = check_login_state_handler(page, context)
        
        assert result is True
        assert context.get("logged_in") is True
    
    def test_handler_returns_false_when_login_url(self):
        """Handler should return False when URL contains '/login'."""
        # Mock page object
        class MockPage:
            url = "https://www.linkedin.com/login/"
        
        page = MockPage()
        context = {}
        
        result = check_login_state_handler(page, context)
        
        assert result is False
        assert context.get("logged_in") is False
    
    def test_handler_is_case_insensitive(self):
        """Handler should be case-insensitive for URL checking."""
        # Mock page object with uppercase LOGIN
        class MockPage:
            url = "https://www.linkedin.com/LOGIN/"
        
        page = MockPage()
        context = {}
        
        result = check_login_state_handler(page, context)
        
        assert result is False
        assert context.get("logged_in") is False
    
    def test_handler_updates_context(self):
        """Handler should update context with logged_in status."""
        class MockPage:
            url = "https://www.linkedin.com/feed/"
        
        page = MockPage()
        context = {}
        
        check_login_state_handler(page, context)
        
        assert "logged_in" in context
        assert isinstance(context["logged_in"], bool)
