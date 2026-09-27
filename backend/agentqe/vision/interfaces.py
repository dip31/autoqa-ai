"""
Vision Module Interfaces — Model-neutral abstraction for visual UI parsing.

All AgentQE code must depend on this interface, not directly on OmniParser.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class VisualUIParser(ABC):
    """
    Abstract base class for visual UI parsers.
    
    Implementations (OmniParserAdapter, etc.) parse screenshot images
    and return normalized VisualUIEvidence.
    """
    
    @abstractmethod
    def parse(
        self,
        screenshot_path: str,
        screenshot_metadata: Dict[str, Any]
    ) -> "VisualUIEvidence":
        """
        Parse a screenshot and extract visual UI elements.
        
        Args:
            screenshot_path: Absolute path to the screenshot file (PNG).
            screenshot_metadata: Dict with keys:
                - sha256: str — SHA256 hash of screenshot file
                - width: int — image width in pixels
                - height: int — image height in pixels
                - capture_type: str — "viewport" or "full_page"
                - format: str — "png"
                - size_bytes: int — file size
                - timestamp: float — capture time
                - page_url: str — source page URL
        
        Returns:
            VisualUIEvidence with normalized elements and parser metadata.
        
        Raises:
            VisualUIParserError: On unrecoverable parsing failure.
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the parser runtime is available.
        
        Returns:
            True if parser can be invoked, False otherwise.
        """
        pass
    
    @abstractmethod
    def get_parser_info(self) -> Dict[str, Any]:
        """
        Get parser metadata for evidence tracking.
        
        Returns:
            Dict with keys:
                - parser: str — parser identifier (e.g., "omniparser")
                - parser_version: str — version/commit
                - model_version: str — detector/caption model versions
        """
        pass


class VisualUIParserError(Exception):
    """Exception raised by VisualUIParser implementations."""
    
    def __init__(self, message: str, error_code: str = "PARSER_ERROR"):
        super().__init__(message)
        self.error_code = error_code
        self.message = message