"""Notification service for macOS desktop notifications.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


class NotificationService:
    """Sends macOS desktop notifications using osascript."""

    def notify(self, title: str, message: str) -> None:
        """
        Send a desktop notification (Requirements 6.1, 6.2, 6.3).

        Args:
            title: Notification title
            message: Notification body text
        """
        try:
            # Construct osascript command for macOS notification
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                text=True,
                timeout=5.0,
            )
            logger.info(f"Notification sent: {title} - {message}")
        except subprocess.CalledProcessError as e:
            # Requirement 6.4: Log failure but continue execution
            logger.warning(
                f"Failed to send notification: {e.stderr if e.stderr else str(e)}"
            )
        except subprocess.TimeoutExpired:
            # Requirement 6.4: Log timeout but continue execution
            logger.warning("Notification command timed out")
        except Exception as e:
            # Requirement 6.4: Log any other failure but continue execution
            logger.warning(f"Unexpected error sending notification: {e}")

    def notify_checkpoint(self, url: str) -> None:
        """
        Send checkpoint detection notification (Requirement 6.1).

        Args:
            url: Current URL where checkpoint was detected
        """
        title = "LinkedIn Bot"
        message = f"Security checkpoint detected at: {url}"
        self.notify(title, message)

    def notify_error(self, error: Exception) -> None:
        """
        Send error notification (Requirements 6.2, 6.5).

        Args:
            error: Exception that occurred
        """
        title = "LinkedIn Bot"
        error_type = type(error).__name__
        message = f"Error ({error_type}): {str(error)}"
        self.notify(title, message)
