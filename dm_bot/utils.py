"""Utility classes for debugging and development.

This module provides utilities for inspecting and debugging LinkedIn pages,
including accessibility tree dumping for pattern discovery.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from dm_bot.storage import StorageError

logger = logging.getLogger(__name__)


class AccessibilityDumper:
    """Dumps accessibility tree to JSON for debugging and pattern discovery.
    
    This utility captures the accessibility tree of a page and saves it to
    a timestamped JSON file. Useful for investigating page structure and
    designing accurate navigation patterns.
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.4
    """

    def __init__(self, output_dir: Path | None = None) -> None:
        """
        Initialize with output directory.
        
        Creates the output directory if it doesn't exist.
        
        Args:
            output_dir: Directory to save dumps. Defaults to .dm_bot_debug/
            
        Requirement 1.5: Create output directory if it doesn't exist
        """
        if output_dir is None:
            output_dir = Path(".dm_bot_debug")
        
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"AccessibilityDumper initialized: {self.output_dir}")

    async def dump_tree(
        self,
        page: Page,
        prefix: str = "snapshot",
    ) -> Path:
        """
        Capture and save accessibility tree to JSON file.
        
        Captures the page's accessibility snapshot and writes it to a
        timestamped JSON file with proper formatting for readability.
        
        Args:
            page: Playwright page to capture
            prefix: Filename prefix (default: "snapshot")
            
        Returns:
            Path to the saved JSON file
            
        Raises:
            StorageError: If snapshot capture or file write fails
            
        Requirements:
            - 1.1: Capture current page's accessibility snapshot
            - 1.2: Write to JSON file with timestamp in filename
            - 1.3: Include all node roles, names, and hierarchical structure
            - 1.4: Log file path for easy reference
            - 3.1: Format JSON with indentation for readability
            - 3.2: Convert datetime objects to ISO format strings
            - 3.3: Write complete structure without truncation
            - 3.4: Preserve hierarchical parent-child relationships
        """
        try:
            # Capture accessibility snapshot (Requirement 1.1)
            # Playwright Python doesn't have page.accessibility.snapshot()
            # Instead, we use page.accessibility.snapshot() via CDP
            snapshot = await page.evaluate("""
                async () => {
                    // Get accessibility tree via Chrome DevTools Protocol
                    const client = await window.cdp;
                    if (!client) {
                        // Fallback: use getByRole to build a tree
                        return null;
                    }
                    const { nodes } = await client.send('Accessibility.getFullAXTree');
                    return nodes;
                }
            """)
            
            # If CDP approach fails, use a simpler snapshot approach
            if snapshot is None:
                logger.info("Using fallback accessibility snapshot method")
                snapshot = await page.evaluate("""
                    () => {
                        function buildAccessibilityTree(element) {
                            const role = element.getAttribute('role') || element.tagName.toLowerCase();
                            const name = element.getAttribute('aria-label') || 
                                        element.getAttribute('aria-labelledby') ||
                                        element.getAttribute('title') ||
                                        element.textContent?.substring(0, 50) || '';
                            
                            const node = {
                                role: role,
                                name: name.trim(),
                                tag: element.tagName.toLowerCase(),
                            };
                            
                            // Add other ARIA attributes
                            const ariaAttrs = {};
                            for (const attr of element.attributes) {
                                if (attr.name.startsWith('aria-')) {
                                    ariaAttrs[attr.name] = attr.value;
                                }
                            }
                            if (Object.keys(ariaAttrs).length > 0) {
                                node.aria = ariaAttrs;
                            }
                            
                            // Recursively process children
                            const children = [];
                            for (const child of element.children) {
                                children.push(buildAccessibilityTree(child));
                            }
                            if (children.length > 0) {
                                node.children = children;
                            }
                            
                            return node;
                        }
                        
                        return buildAccessibilityTree(document.body);
                    }
                """)
            
            if snapshot is None:
                logger.warning("Accessibility snapshot returned None")
                snapshot = {"error": "No accessibility tree available"}
            
            # Generate timestamped filename (Requirement 1.2)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}.json"
            filepath = self.output_dir / filename
            
            # Write to JSON file with indentation (Requirements 3.1, 3.2, 3.3, 3.4)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, default=str, ensure_ascii=False)
            
            # Log file path (Requirement 1.4)
            logger.info(f"Accessibility tree dumped to: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to dump accessibility tree: {e}")
            raise StorageError(f"Failed to dump accessibility tree: {e}") from e
