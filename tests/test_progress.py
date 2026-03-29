"""
Property-based tests for ProgressReporter.

This module tests the output format completeness of the ProgressReporter class
to ensure all required information is displayed during sync operations.

Requirements: 1.3, 3.1, 3.2, 3.3, 3.4
"""

import io
import sys
from datetime import datetime, timedelta
from typing import Any

import pytest
from hypothesis import given, strategies as st

from dm_bot.main import ProgressReporter


@given(
    index=st.integers(min_value=1, max_value=100),
    total=st.integers(min_value=1, max_value=100),
    name=st.text(min_size=1, max_size=100),
    message_count=st.integers(min_value=0, max_value=1000),
    new_messages=st.integers(min_value=0, max_value=1000),
    skipped_messages=st.integers(min_value=0, max_value=1000),
    errors=st.lists(st.text(min_size=1, max_size=200), max_size=10),
)
def test_output_format_completeness(
    index: int,
    total: int,
    name: str,
    message_count: int,
    new_messages: int,
    skipped_messages: int,
    errors: list[str],
) -> None:
    """
    **Feature: sync-command, Property 1: Output format completeness**
    
    For any sync execution that processes N conversations and stores M messages,
    the output should contain progress messages for each conversation, message counts,
    and a final summary with conversations processed, messages stored, messages skipped,
    and elapsed time.
    
    **Validates: Requirements 1.3, 3.1, 3.2, 3.3, 3.4**
    """
    # Constrain index to be <= total for valid progress
    if index > total:
        index, total = total, index
    
    # Capture stdout
    captured_output = io.StringIO()
    sys.stdout = captured_output
    
    try:
        # Create reporter
        reporter = ProgressReporter()
        
        # Simulate a sync operation
        reporter.report_conversation_start(index, total, name)
        reporter.report_messages_extracted(message_count)
        reporter.report_messages_stored(new_messages, skipped_messages)
        
        # Report any errors
        for error in errors:
            reporter.report_error(error)
        
        # Report final summary
        reporter.report_final_summary(errors)
        
        # Get output
        output = captured_output.getvalue()
        
        # Verify progress message contains required elements (Requirement 3.1)
        assert f"Processing {index}/{total}" in output, \
            "Output should contain progress count"
        assert name in output, \
            "Output should contain connection name"
        
        # Verify message extraction count (Requirement 3.2)
        assert f"Found {message_count} messages" in output, \
            "Output should contain number of messages found"
        
        # Verify storage results (Requirement 3.3)
        assert f"Stored {new_messages} new" in output, \
            "Output should contain number of new messages stored"
        assert f"skipped {skipped_messages} duplicates" in output, \
            "Output should contain number of duplicate messages skipped"
        
        # Verify final summary contains all required fields (Requirements 1.3, 3.4)
        assert "Sync Complete" in output, \
            "Output should contain completion message"
        assert "Conversations processed:" in output, \
            "Output should contain conversations processed count"
        assert "Messages stored:" in output, \
            "Output should contain messages stored count"
        assert "Messages skipped (duplicates):" in output, \
            "Output should contain messages skipped count"
        assert "Time elapsed:" in output, \
            "Output should contain elapsed time"
        
        # Verify error reporting
        if errors:
            assert "Errors encountered:" in output, \
                "Output should contain error count when errors occur"
            # At least some errors should be displayed
            for error in errors[:5]:  # First 5 errors should be shown
                assert error in output, \
                    f"Output should contain error message: {error}"
        
        # Verify counters are updated correctly
        assert reporter.conversations_processed == 1, \
            "Conversations processed counter should be incremented"
        assert reporter.messages_stored == new_messages, \
            "Messages stored counter should match new messages"
        assert reporter.messages_skipped == skipped_messages, \
            "Messages skipped counter should match skipped messages"
        
    finally:
        # Restore stdout
        sys.stdout = sys.__stdout__


def test_progress_reporter_multiple_conversations() -> None:
    """
    Test that ProgressReporter correctly accumulates statistics across multiple conversations.
    
    This is a unit test to verify the accumulation logic works correctly.
    """
    # Capture stdout
    captured_output = io.StringIO()
    sys.stdout = captured_output
    
    try:
        reporter = ProgressReporter()
        
        # Process first conversation
        reporter.report_conversation_start(1, 3, "Alice")
        reporter.report_messages_extracted(10)
        reporter.report_messages_stored(8, 2)
        
        # Process second conversation
        reporter.report_conversation_start(2, 3, "Bob")
        reporter.report_messages_extracted(5)
        reporter.report_messages_stored(5, 0)
        
        # Process third conversation
        reporter.report_conversation_start(3, 3, "Charlie")
        reporter.report_messages_extracted(7)
        reporter.report_messages_stored(3, 4)
        
        # Verify accumulated statistics
        assert reporter.conversations_processed == 3
        assert reporter.messages_stored == 16  # 8 + 5 + 3
        assert reporter.messages_skipped == 6  # 2 + 0 + 4
        
        # Report final summary
        reporter.report_final_summary([])
        
        output = captured_output.getvalue()
        
        # Verify final summary reflects accumulated statistics
        assert "Conversations processed: 3" in output
        assert "Messages stored: 16" in output
        assert "Messages skipped (duplicates): 6" in output
        
    finally:
        sys.stdout = sys.__stdout__


def test_progress_reporter_elapsed_time() -> None:
    """
    Test that ProgressReporter correctly calculates and displays elapsed time.
    
    This is a unit test to verify time tracking works correctly.
    """
    # Capture stdout
    captured_output = io.StringIO()
    sys.stdout = captured_output
    
    try:
        reporter = ProgressReporter()
        start_time = reporter.start_time
        
        # Verify start time is recent (within last second)
        now = datetime.now()
        assert (now - start_time).total_seconds() < 1.0
        
        # Report final summary
        reporter.report_final_summary([])
        
        output = captured_output.getvalue()
        
        # Verify elapsed time is displayed
        assert "Time elapsed:" in output
        
    finally:
        sys.stdout = sys.__stdout__


def test_progress_reporter_error_truncation() -> None:
    """
    Test that ProgressReporter truncates error list when there are more than 5 errors.
    
    This is a unit test to verify error display logic.
    """
    # Capture stdout and stderr
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    sys.stdout = captured_stdout
    sys.stderr = captured_stderr
    
    try:
        reporter = ProgressReporter()
        
        # Create 10 errors
        errors = [f"Error {i}" for i in range(10)]
        
        # Report final summary
        reporter.report_final_summary(errors)
        
        output = captured_stdout.getvalue()
        
        # Verify error count is displayed
        assert "Errors encountered: 10" in output
        
        # Verify first 5 errors are shown
        for i in range(5):
            assert f"Error {i}" in output
        
        # Verify truncation message is shown
        assert "and 5 more" in output
        
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
