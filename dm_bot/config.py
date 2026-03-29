"""Configuration module with constants for delays, timeouts, and paths."""

import os
import random
import time
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# ============================================================================
# Credentials
# ============================================================================

LI_USER: Optional[str] = os.getenv("LI_USER")
LI_PASS: Optional[str] = os.getenv("LI_PASS")


# ============================================================================
# Browser Configuration
# ============================================================================

# Mobile viewport (iPhone 5/SE)
VIEWPORT_WIDTH: int = 320
VIEWPORT_HEIGHT: int = 568

# User agent string for iPhone 5/SE
USER_AGENT: str = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) "
    "AppleWebKit/603.1.30 (KHTML, like Gecko) "
    "Version/10.0 Mobile/14E304 Safari/602.1"
)

# Browser profile path
_PERSISTENCE_DIR: Path = Path(__file__).parent.parent / ".persistence"
DEFAULT_PROFILE_PATH: Path = _PERSISTENCE_DIR / "browser_profile"
PROFILE_PATH: Path = Path(
    os.getenv("DM_BOT_PROFILE_PATH", str(DEFAULT_PROFILE_PATH))
)


# ============================================================================
# Database Configuration (Requirement 4.4)
# ============================================================================

# Database file path
DEFAULT_DB_PATH: Path = _PERSISTENCE_DIR / "dm_bot.db"
DB_PATH: Path = Path(os.getenv("DM_BOT_DB_PATH", str(DEFAULT_DB_PATH)))

# Headless mode
HEADLESS: bool = os.getenv("DM_BOT_HEADLESS", "false").lower() == "true"


# ============================================================================
# Delay Configuration (Requirements 4.1, 4.2, 4.3, 4.4)
# ============================================================================

# Delay between UI actions (seconds)
DELAY_MIN: float = float(os.getenv("DM_BOT_DELAY_MIN", "2.0"))
DELAY_MAX: float = float(os.getenv("DM_BOT_DELAY_MAX", "5.0"))

# Per-character typing delay (seconds)
TYPING_DELAY_MIN: float = 0.05
TYPING_DELAY_MAX: float = 0.15

# Delay after page load (seconds)
PAGE_LOAD_DELAY_MIN: float = 1.5
PAGE_LOAD_DELAY_MAX: float = 3.0

# Delay between opening conversations (seconds)
CONVERSATION_DELAY_MIN: float = 5.0
CONVERSATION_DELAY_MAX: float = 10.0


# ============================================================================
# Rate Limiting Configuration (Requirement 4.5)
# ============================================================================

MAX_ACTIONS_PER_MINUTE: int = int(
    os.getenv("DM_BOT_MAX_ACTIONS_PER_MINUTE", "20")
)


# ============================================================================
# Timeout Configuration
# ============================================================================

# Default element wait timeout (milliseconds)
DEFAULT_TIMEOUT_MS: int = 10000

# Navigation timeout (milliseconds)
NAVIGATION_TIMEOUT_MS: int = 30000


# ============================================================================
# Retry Configuration (Requirements 5.1, 5.2)
# ============================================================================

# Maximum retry attempts for actions
MAX_RETRY_ATTEMPTS: int = 3

# Base delay for exponential backoff (seconds)
BACKOFF_BASE_DELAY: float = 5.0


# ============================================================================
# Checkpoint Detection Patterns (Requirements 2.2, 2.3, 2.4)
# ============================================================================

CHECKPOINT_PATTERNS: list[str] = [
    "/checkpoint/",  # Security verification pages
    "/authwall",     # Authentication barriers
    # Note: "/login" is NOT a checkpoint - it's checked separately in login verification
]


# ============================================================================
# Logging Configuration (Requirement 8.5)
# ============================================================================

LOG_LEVEL: str = os.getenv("DM_BOT_LOG_LEVEL", "INFO")
LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
LOG_FILE: Optional[str] = os.getenv("DM_BOT_LOG_FILE", "dm_bot.log")


# ============================================================================
# Rate Limiter Class
# ============================================================================

class RateLimiter:
    """Manages action delays and rate limiting."""

    def __init__(
        self,
        delay_range: tuple[float, float] = (DELAY_MIN, DELAY_MAX),
        max_actions_per_minute: int = MAX_ACTIONS_PER_MINUTE,
    ):
        """
        Initialize rate limiter.

        Args:
            delay_range: Tuple of (min, max) delay in seconds between actions
            max_actions_per_minute: Maximum number of actions allowed per minute
        """
        self.delay_min, self.delay_max = delay_range
        self.max_actions = max_actions_per_minute
        self.action_timestamps: list[float] = []
        
        # Statistics tracking (Requirement 5.4)
        self.total_actions = 0
        self.total_delay = 0.0

    async def delay_between_actions(self) -> None:
        """Apply random delay between actions (Requirement 4.1)."""
        delay = random.uniform(self.delay_min, self.delay_max)
        await asyncio.sleep(delay)
        
        # Track statistics (Requirement 5.4)
        self.total_actions += 1
        self.total_delay += delay

    async def delay_for_typing(self, text: str) -> None:
        """
        Apply per-character typing delays (Requirement 4.2).

        Args:
            text: Text being typed
        """
        total_delay = 0.0
        for _ in text:
            delay = random.uniform(TYPING_DELAY_MIN, TYPING_DELAY_MAX)
            await asyncio.sleep(delay)
            total_delay += delay
        
        # Track statistics (Requirement 5.4)
        self.total_actions += 1
        self.total_delay += total_delay

    async def delay_after_page_load(self) -> None:
        """Apply delay after page navigation (Requirement 4.3)."""
        delay = random.uniform(PAGE_LOAD_DELAY_MIN, PAGE_LOAD_DELAY_MAX)
        await asyncio.sleep(delay)
        
        # Track statistics (Requirement 5.4)
        self.total_actions += 1
        self.total_delay += delay

    async def delay_for_conversation(self) -> None:
        """Apply delay between opening conversations (Requirement 4.4)."""
        delay = random.uniform(CONVERSATION_DELAY_MIN, CONVERSATION_DELAY_MAX)
        await asyncio.sleep(delay)
        
        # Track statistics (Requirement 5.4)
        self.total_actions += 1
        self.total_delay += delay

    async def check_rate_limit(self) -> None:
        """
        Pause if action rate exceeds limit (Requirement 4.5).

        Implements sliding window rate limiting. If the number of actions
        in the last 60 seconds exceeds the limit, pauses until the rate
        falls below the threshold.
        """
        now = time.time()

        # Remove timestamps older than 60 seconds
        self.action_timestamps = [
            ts for ts in self.action_timestamps if now - ts < 60.0
        ]

        if len(self.action_timestamps) >= self.max_actions:
            # Calculate pause duration
            oldest = self.action_timestamps[0]
            pause = 60.0 - (now - oldest) + 0.1  # Add small buffer
            await asyncio.sleep(pause)

            # Clean up again after pause
            now = time.time()
            self.action_timestamps = [
                ts for ts in self.action_timestamps if now - ts < 60.0
            ]

        # Record this action
        self.action_timestamps.append(now)
    
    def get_statistics(self) -> dict[str, float]:
        """
        Get rate limiting statistics.
        
        Returns:
            Dictionary with 'total_actions', 'total_delay', and 'average_delay'
            
        Requirement 5.4: Log total actions performed and average delay applied
        """
        average_delay = self.total_delay / self.total_actions if self.total_actions > 0 else 0.0
        return {
            "total_actions": self.total_actions,
            "total_delay": self.total_delay,
            "average_delay": average_delay,
        }


# ============================================================================
# Utility Functions
# ============================================================================

def calculate_backoff_delay(attempt: int) -> float:
    """
    Calculate exponential backoff delay (Requirement 5.2).

    Args:
        attempt: Retry attempt number (0-indexed)

    Returns:
        Delay in seconds: 5.0 × (2 ^ attempt)
    """
    return BACKOFF_BASE_DELAY * (2**attempt)


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    log_date_format: Optional[str] = None,
) -> None:
    """
    Configure Python logging with file and console handlers.
    
    Sets up logging with:
    - Console handler (stdout) for all log levels
    - File handler for persistent logs
    - Consistent timestamp format: "YYYY-MM-DD HH:MM:SS"
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                  Defaults to LOG_LEVEL from config.
        log_file: Path to log file. Defaults to LOG_FILE from config.
        log_format: Log message format. Defaults to LOG_FORMAT from config.
        log_date_format: Timestamp format. Defaults to LOG_DATE_FORMAT from config.
    
    Requirements:
        - 8.1: Log action name, type, and target element at INFO level
        - 8.2: Log failures at WARNING level with retry attempt number
        - 8.3: Log checkpoint detection at ERROR level with URL
        - 8.4: Log configuration parameters at INFO level on startup
        - 8.5: Include timestamps in format "YYYY-MM-DD HH:MM:SS"
    """
    # Use defaults from config if not provided
    if log_level is None:
        log_level = LOG_LEVEL
    if log_file is None:
        log_file = LOG_FILE
    if log_format is None:
        log_format = LOG_FORMAT
    if log_date_format is None:
        log_date_format = LOG_DATE_FORMAT
    
    # Convert string log level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create formatter with timestamp format (Requirement 8.5)
    formatter = logging.Formatter(
        fmt=log_format,
        datefmt=log_date_format,
    )
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Create console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Create file handler if log_file is specified
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, mode='a')
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            # Log to console if file handler creation fails
            root_logger.error(f"Failed to create file handler for {log_file}: {e}")
    
    # Log startup configuration (Requirement 8.4)
    root_logger.info("=" * 60)
    root_logger.info("DM Bot Logging Initialized")
    root_logger.info(f"Log Level: {log_level}")
    root_logger.info(f"Log File: {log_file}")
    root_logger.info(f"Timestamp Format: {log_date_format}")
    root_logger.info("=" * 60)

