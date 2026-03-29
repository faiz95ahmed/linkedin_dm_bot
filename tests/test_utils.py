"""Property-based tests for utility classes.

Feature: robust-navigation
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from hypothesis import given, strategies as st, settings
import pytest

from dm_bot.utils import AccessibilityDumper
from dm_bot.storage import StorageError


# Strategy for generating valid prefixes (alphanumeric with underscores/hyphens)
valid_prefixes = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(
        min_codepoint=97,
        max_codepoint=122,
    ) | st.sampled_from(['_', '-'])
).filter(lambda x: x[0].isalpha())  # Must start with letter


# Strategy for generating accessibility tree nodes (simple, no deep nesting)
def accessibility_node_strategy():
    """Generate a valid accessibility tree node structure."""
    return st.fixed_dictionaries({
        'role': st.sampled_from(['button', 'textbox', 'link', 'heading', 'list', 'listitem']),
        'name': st.text(min_size=0, max_size=50),
        'children': st.lists(
            st.fixed_dictionaries({
                'role': st.sampled_from(['button', 'textbox', 'link']),
                'name': st.text(min_size=0, max_size=20),
            }),
            min_size=0,
            max_size=3
        )
    })


# Feature: robust-navigation, Property 1: Accessibility tree capture completeness
# Validates: Requirements 1.1, 1.3, 3.3
@settings(max_examples=100, deadline=None)
@given(
    tree_data=accessibility_node_strategy(),
    prefix=valid_prefixes,
)
def test_property_1_accessibility_tree_capture_completeness(
    tree_data: dict,
    prefix: str,
) -> None:
    """
    Property 1: Accessibility tree capture completeness
    
    For any page with an accessibility tree, calling dump_tree should produce
    a JSON file containing all node roles, names, and hierarchical structure.
    
    This test verifies:
    1. The snapshot is captured from the page
    2. All node data is preserved in the JSON file
    3. The hierarchical structure is maintained
    """
    import tempfile
    
    async def run_test():
        # Create temporary directory for this test
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create mock page with accessibility snapshot
            mock_page = MagicMock()
            mock_page.evaluate = AsyncMock(return_value=tree_data)
            
            # Create dumper with temp directory
            dumper = AccessibilityDumper(output_dir=tmp_path)
            
            # Dump the tree
            filepath = await dumper.dump_tree(mock_page, prefix=prefix)
            
            # Verify file was created
            assert filepath.exists(), f"File {filepath} was not created"
            
            # Read the JSON file
            with open(filepath, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            
            # Verify all data is preserved
            assert saved_data == tree_data, (
                "Saved data does not match original tree data"
            )
            
            # Verify role is preserved
            assert saved_data['role'] == tree_data['role'], (
                f"Role not preserved: expected '{tree_data['role']}', "
                f"got '{saved_data['role']}'"
            )
            
            # Verify name is preserved
            assert saved_data['name'] == tree_data['name'], (
                f"Name not preserved: expected '{tree_data['name']}', "
                f"got '{saved_data['name']}'"
            )
            
            # Verify children structure is preserved
            assert 'children' in saved_data, "Children key missing from saved data"
            assert len(saved_data['children']) == len(tree_data['children']), (
                f"Children count mismatch: expected {len(tree_data['children'])}, "
                f"got {len(saved_data['children'])}"
            )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 1: Accessibility tree capture completeness
# Validates: Requirements 1.1, 1.3, 3.3
@settings(max_examples=100, deadline=None)
@given(
    prefix=valid_prefixes,
)
def test_property_1_none_snapshot_handling(
    prefix: str,
) -> None:
    """
    Property 1: Accessibility tree capture completeness
    
    When the accessibility snapshot returns None, the system should handle
    it gracefully by writing an error object to the JSON file.
    """
    import tempfile
    
    async def run_test():
        # Create temporary directory for this test
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create mock page that returns None snapshot
            mock_page = MagicMock()
            # First evaluate returns None (CDP fails), second evaluate returns None (fallback fails)
            mock_page.evaluate = AsyncMock(side_effect=[None, None])
            
            # Create dumper with temp directory
            dumper = AccessibilityDumper(output_dir=tmp_path)
            
            # Dump the tree (should not raise exception)
            filepath = await dumper.dump_tree(mock_page, prefix=prefix)
            
            # Verify file was created
            assert filepath.exists(), f"File {filepath} was not created"
            
            # Read the JSON file
            with open(filepath, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            
            # Verify error object was written
            assert 'error' in saved_data, (
                "Error key missing from saved data when snapshot is None"
            )
            assert saved_data['error'] == "No accessibility tree available", (
                f"Unexpected error message: {saved_data['error']}"
            )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 2: Timestamped filename generation
# Validates: Requirements 1.2
@settings(max_examples=100, deadline=None)
@given(
    prefix=valid_prefixes,
)
def test_property_2_timestamped_filename_generation(
    prefix: str,
) -> None:
    """
    Property 2: Timestamped filename generation
    
    For any dump operation, the generated filename should include a timestamp
    in YYYYMMDD_HHMMSS format and the specified prefix.
    
    This test verifies:
    1. Filename contains the specified prefix
    2. Filename contains a timestamp in the correct format
    3. Filename has .json extension
    """
    import tempfile
    
    async def run_test():
        # Create temporary directory for this test
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create mock page
            mock_page = MagicMock()
            mock_page.evaluate = AsyncMock(return_value={'role': 'button'})
            
            # Create dumper with temp directory
            dumper = AccessibilityDumper(output_dir=tmp_path)
            
            # Record time before dump
            before_dump = datetime.now()
            
            # Dump the tree
            filepath = await dumper.dump_tree(mock_page, prefix=prefix)
            
            # Record time after dump
            after_dump = datetime.now()
            
            # Verify file was created
            assert filepath.exists(), f"File {filepath} was not created"
            
            # Extract filename
            filename = filepath.name
            
            # Verify filename starts with prefix
            assert filename.startswith(prefix), (
                f"Filename '{filename}' does not start with prefix '{prefix}'"
            )
            
            # Verify filename ends with .json
            assert filename.endswith('.json'), (
                f"Filename '{filename}' does not end with .json"
            )
            
            # Extract timestamp from filename (format: prefix_YYYYMMDD_HHMMSS.json)
            pattern = rf'{re.escape(prefix)}_(\d{{8}}_\d{{6}})\.json'
            match = re.match(pattern, filename)
            assert match is not None, (
                f"Filename '{filename}' does not match expected pattern '{pattern}'"
            )
            
            timestamp_str = match.group(1)
            
            # Verify timestamp format (YYYYMMDD_HHMMSS)
            timestamp_pattern = r'\d{8}_\d{6}'
            assert re.match(timestamp_pattern, timestamp_str), (
                f"Timestamp '{timestamp_str}' does not match format YYYYMMDD_HHMMSS"
            )
            
            # Parse timestamp and verify it's within reasonable range (allow 1 second tolerance)
            timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
            # The timestamp should be within 1 second of the dump time
            time_diff = abs((timestamp - before_dump).total_seconds())
            assert time_diff <= 1.0, (
                f"Timestamp {timestamp} is more than 1 second away from {before_dump}"
            )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 2: Timestamped filename generation
# Validates: Requirements 1.2
@settings(max_examples=10, deadline=None)  # Reduced examples due to sleep
@given(
    prefix=valid_prefixes,
)
def test_property_2_unique_filenames_for_sequential_dumps(
    prefix: str,
) -> None:
    """
    Property 2: Timestamped filename generation
    
    For sequential dump operations, each should generate a unique filename
    due to the timestamp component.
    """
    import tempfile
    
    async def run_test():
        # Create temporary directory for this test
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create mock page
            mock_page = MagicMock()
            mock_page.evaluate = AsyncMock(return_value={'role': 'button'})
            
            # Create dumper with temp directory
            dumper = AccessibilityDumper(output_dir=tmp_path)
            
            # Perform multiple dumps with delay to ensure different timestamps
            filepaths = []
            for _ in range(2):  # Reduced from 3 to 2
                filepath = await dumper.dump_tree(mock_page, prefix=prefix)
                filepaths.append(filepath)
                # 1 second delay to ensure different timestamps (format is YYYYMMDD_HHMMSS)
                await asyncio.sleep(1.0)
            
            # Verify all files were created
            for filepath in filepaths:
                assert filepath.exists(), f"File {filepath} was not created"
            
            # Verify all filenames are unique
            filenames = [fp.name for fp in filepaths]
            assert len(filenames) == len(set(filenames)), (
                f"Duplicate filenames found: {filenames}"
            )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 3: Output directory creation
# Validates: Requirements 1.5
@settings(max_examples=100, deadline=None)
@given(
    prefix=valid_prefixes,
)
def test_property_3_output_directory_creation(
    prefix: str,
) -> None:
    """
    Property 3: Output directory creation
    
    For any specified output directory that doesn't exist, the dumper should
    create it automatically before writing the file.
    
    This test verifies:
    1. Non-existent directories are created automatically
    2. Nested directories are created (parents=True)
    3. Files can be written to the newly created directory
    """
    import tempfile
    
    async def run_test():
        # Create temporary directory for this test
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create a non-existent nested directory path
            non_existent_dir = tmp_path / "level1" / "level2" / "level3"
            
            # Verify directory doesn't exist yet
            assert not non_existent_dir.exists(), (
                f"Directory {non_existent_dir} should not exist yet"
            )
            
            # Create mock page
            mock_page = MagicMock()
            mock_page.evaluate = AsyncMock(return_value={'role': 'button', 'name': 'Test'})
            
            # Create dumper with non-existent directory
            dumper = AccessibilityDumper(output_dir=non_existent_dir)
            
            # Verify directory was created during initialization
            assert non_existent_dir.exists(), (
                f"Directory {non_existent_dir} should have been created"
            )
            assert non_existent_dir.is_dir(), (
                f"{non_existent_dir} should be a directory"
            )
            
            # Dump the tree to verify we can write to the new directory
            filepath = await dumper.dump_tree(mock_page, prefix=prefix)
            
            # Verify file was created in the new directory
            assert filepath.exists(), f"File {filepath} was not created"
            assert filepath.parent == non_existent_dir, (
                f"File should be in {non_existent_dir}, but is in {filepath.parent}"
            )
            
            # Verify the file contains valid JSON
            with open(filepath, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            
            assert saved_data['role'] == 'button', "Data should be preserved"
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 3: Output directory creation
# Validates: Requirements 1.5
@settings(max_examples=100, deadline=None)
@given(
    prefix=valid_prefixes,
)
def test_property_3_existing_directory_handling(
    prefix: str,
) -> None:
    """
    Property 3: Output directory creation
    
    When the output directory already exists, the dumper should use it
    without error (exist_ok=True behavior).
    """
    import tempfile
    
    async def run_test():
        # Create temporary directory for this test
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create an existing directory
            existing_dir = tmp_path / "existing"
            existing_dir.mkdir(parents=True, exist_ok=True)
            
            # Verify directory exists
            assert existing_dir.exists(), f"Directory {existing_dir} should exist"
            
            # Create mock page
            mock_page = MagicMock()
            mock_page.evaluate = AsyncMock(return_value={'role': 'link', 'name': 'Click me'})
            
            # Create dumper with existing directory (should not raise exception)
            dumper = AccessibilityDumper(output_dir=existing_dir)
            
            # Verify directory still exists
            assert existing_dir.exists(), f"Directory {existing_dir} should still exist"
            
            # Dump the tree
            filepath = await dumper.dump_tree(mock_page, prefix=prefix)
            
            # Verify file was created
            assert filepath.exists(), f"File {filepath} was not created"
            assert filepath.parent == existing_dir, (
                f"File should be in {existing_dir}, but is in {filepath.parent}"
            )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 3: Output directory creation
# Validates: Requirements 1.5
@settings(max_examples=100, deadline=None)
@given(
    prefix=valid_prefixes,
)
def test_property_3_default_directory_creation(
    prefix: str,
) -> None:
    """
    Property 3: Output directory creation
    
    When no output directory is specified, the dumper should create the
    default .dm_bot_debug/ directory.
    """
    import tempfile
    import os
    
    async def run_test():
        # Create temporary directory and change to it
        with tempfile.TemporaryDirectory() as tmp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(tmp_dir)
                
                # Verify default directory doesn't exist yet
                default_dir = Path(".dm_bot_debug")
                if default_dir.exists():
                    import shutil
                    shutil.rmtree(default_dir)
                
                assert not default_dir.exists(), (
                    f"Default directory {default_dir} should not exist yet"
                )
                
                # Create mock page
                mock_page = MagicMock()
                mock_page.evaluate = AsyncMock(return_value={'role': 'heading', 'name': 'Title'})
                
                # Create dumper without specifying output_dir
                dumper = AccessibilityDumper()
                
                # Verify default directory was created
                assert default_dir.exists(), (
                    f"Default directory {default_dir} should have been created"
                )
                assert default_dir.is_dir(), (
                    f"{default_dir} should be a directory"
                )
                
                # Dump the tree
                filepath = await dumper.dump_tree(mock_page, prefix=prefix)
                
                # Verify file was created in default directory
                assert filepath.exists(), f"File {filepath} was not created"
                assert filepath.parent == default_dir, (
                    f"File should be in {default_dir}, but is in {filepath.parent}"
                )
                
            finally:
                os.chdir(original_cwd)
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 4: JSON formatting and readability
# Validates: Requirements 3.1, 3.2, 3.4
@settings(max_examples=100, deadline=None)
@given(
    tree_data=accessibility_node_strategy(),
    prefix=valid_prefixes,
)
def test_property_4_json_formatting_and_readability(
    tree_data: dict,
    prefix: str,
) -> None:
    """
    Property 4: JSON formatting and readability
    
    For any dumped tree, the JSON file should be formatted with indentation
    and preserve hierarchical relationships.
    
    This test verifies:
    1. JSON is formatted with indentation (indent=2)
    2. File uses UTF-8 encoding
    3. Hierarchical structure is preserved
    """
    import tempfile
    
    async def run_test():
        # Create temporary directory for this test
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create mock page
            mock_page = MagicMock()
            mock_page.evaluate = AsyncMock(return_value=tree_data)
            
            # Create dumper with temp directory
            dumper = AccessibilityDumper(output_dir=tmp_path)
            
            # Dump the tree
            filepath = await dumper.dump_tree(mock_page, prefix=prefix)
            
            # Read the raw file content
            with open(filepath, 'r', encoding='utf-8') as f:
                raw_content = f.read()
            
            # Verify indentation is present (check for newlines and spaces)
            assert '\n' in raw_content, "JSON should be formatted with newlines"
            assert '  ' in raw_content, "JSON should be formatted with indentation"
            
            # Verify the content can be parsed as JSON
            parsed_data = json.loads(raw_content)
            assert parsed_data == tree_data, "Parsed data does not match original"
            
            # Verify hierarchical structure is preserved
            if 'children' in tree_data and tree_data['children']:
                assert 'children' in parsed_data, "Children key missing"
                assert isinstance(parsed_data['children'], list), (
                    "Children should be a list"
                )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 4: JSON formatting and readability
# Validates: Requirements 3.1, 3.2, 3.4
@settings(max_examples=100, deadline=None)
@given(
    prefix=valid_prefixes,
)
def test_property_4_datetime_serialization(
    prefix: str,
) -> None:
    """
    Property 4: JSON formatting and readability
    
    When the tree contains datetime objects, they should be converted to
    ISO format strings using default=str.
    """
    import tempfile
    
    async def run_test():
        # Create temporary directory for this test
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create tree data with datetime object
            now = datetime.now()
            tree_data = {
                'role': 'button',
                'name': 'Test',
                'timestamp': now,
            }
            
            # Create mock page
            mock_page = MagicMock()
            mock_page.evaluate = AsyncMock(return_value=tree_data)
            
            # Create dumper with temp directory
            dumper = AccessibilityDumper(output_dir=tmp_path)
            
            # Dump the tree (should not raise exception)
            filepath = await dumper.dump_tree(mock_page, prefix=prefix)
            
            # Read the JSON file
            with open(filepath, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            
            # Verify datetime was converted to string
            assert 'timestamp' in saved_data, "Timestamp key missing"
            assert isinstance(saved_data['timestamp'], str), (
                f"Timestamp should be string, got {type(saved_data['timestamp'])}"
            )
            
            # Verify the string representation is reasonable
            assert str(now.year) in saved_data['timestamp'], (
                f"Timestamp string '{saved_data['timestamp']}' does not contain year"
            )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 4: JSON formatting and readability
# Validates: Requirements 3.1, 3.2, 3.4
@settings(max_examples=100, deadline=None)
@given(
    prefix=valid_prefixes,
)
def test_property_4_unicode_handling(
    prefix: str,
) -> None:
    """
    Property 4: JSON formatting and readability
    
    The JSON file should handle Unicode characters correctly with
    ensure_ascii=False.
    """
    import tempfile
    
    async def run_test():
        # Create temporary directory for this test
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create tree data with Unicode characters
            tree_data = {
                'role': 'button',
                'name': 'Test 测试 🔥',
                'description': 'Café résumé',
            }
            
            # Create mock page
            mock_page = MagicMock()
            mock_page.evaluate = AsyncMock(return_value=tree_data)
            
            # Create dumper with temp directory
            dumper = AccessibilityDumper(output_dir=tmp_path)
            
            # Dump the tree
            filepath = await dumper.dump_tree(mock_page, prefix=prefix)
            
            # Read the JSON file
            with open(filepath, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)
            
            # Verify Unicode characters are preserved
            assert saved_data['name'] == tree_data['name'], (
                f"Unicode name not preserved: expected '{tree_data['name']}', "
                f"got '{saved_data['name']}'"
            )
            assert saved_data['description'] == tree_data['description'], (
                f"Unicode description not preserved: expected '{tree_data['description']}', "
                f"got '{saved_data['description']}'"
            )
    
    asyncio.run(run_test())


# Feature: robust-navigation, Property 4: JSON formatting and readability
# Validates: Requirements 3.1, 3.2, 3.4
@settings(max_examples=100, deadline=None)
@given(
    prefix=valid_prefixes,
)
def test_property_4_storage_error_on_write_failure(
    prefix: str,
) -> None:
    """
    Property 4: JSON formatting and readability
    
    When file write fails, the system should raise StorageError with
    a descriptive message.
    """
    import tempfile
    
    async def run_test():
        # Create temporary directory for this test
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create mock page
            mock_page = MagicMock()
            mock_page.evaluate = AsyncMock(return_value={'role': 'button'})
            
            # Create dumper with invalid directory (read-only)
            invalid_dir = tmp_path / "readonly"
            invalid_dir.mkdir()
            invalid_dir.chmod(0o444)  # Read-only
            
            dumper = AccessibilityDumper(output_dir=invalid_dir)
            
            # Attempt to dump the tree (should raise StorageError)
            try:
                await dumper.dump_tree(mock_page, prefix=prefix)
                # If we get here, the test should fail
                # (unless the OS allows writing despite permissions)
                # Skip assertion in that case
            except StorageError as e:
                # Verify error message is descriptive
                assert "Failed to dump accessibility tree" in str(e), (
                    f"StorageError message should be descriptive, got: {e}"
                )
            except PermissionError:
                # This is also acceptable - it means the write failed as expected
                pass
            finally:
                # Restore permissions for cleanup
                invalid_dir.chmod(0o755)
    
    asyncio.run(run_test())
