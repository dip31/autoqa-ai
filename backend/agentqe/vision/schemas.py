"""
Vision Module Schemas — Normalized visual UI evidence structures.

Independent of OmniParser's raw output format.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional


@dataclass
class VisualUIElement:
    """
    A single visual UI element detected in a screenshot.
    
    Fields mirror what OmniParser can provide, with sensible defaults
    for missing information.
    """
    id: str
    type: str                           # e.g., "button", "input", "icon", "text", "link", "dropdown", "menu", "tab", "checkbox", "radio", "image", "other"
    text: Optional[str] = None          # Visible text content (OCR or caption)
    caption: Optional[str] = None       # Icon caption from vision model
    bbox_pixels: List[int] = field(default_factory=list)    # [x1, y1, x2, y2] in pixels
    bbox_normalized: List[float] = field(default_factory=list)  # [x1, y1, x2, y2] normalized 0.0-1.0
    interactable: Optional[bool] = None # True/False/None if unknown
    confidence: Optional[float] = None  # Detection confidence 0.0-1.0, None if unavailable
    source: str = "omniparser"          # Origin: "omniparser_yolo", "omniparser_ocr", "omniparser_caption"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VisualUIElement":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class VisualUIEvidence:
    """
    Normalized visual UI evidence from a screenshot parse.
    
    This is the canonical structure stored in CrawledPage.visual_ui
    and ApplicationContext.pages[i].visual_ui.
    """
    status: str                         # "success" | "failed" | "skipped" | "unavailable"
    parser: str                         # Parser identifier (e.g., "omniparser")
    parser_version: Optional[str] = None
    model_version: Optional[str] = None
    screenshot_sha256: Optional[str] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    elements: List[VisualUIElement] = field(default_factory=list)
    error_code: Optional[str] = None
    message: Optional[str] = None
    parse_duration_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "parser": self.parser,
            "parser_version": self.parser_version,
            "model_version": self.model_version,
            "screenshot_sha256": self.screenshot_sha256,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "elements": [e.to_dict() for e in self.elements],
            "error_code": self.error_code,
            "message": self.message,
            "parse_duration_ms": self.parse_duration_ms,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VisualUIEvidence":
        elements = [VisualUIElement.from_dict(e) for e in d.get("elements", [])]
        return cls(
            status=d.get("status", "failed"),
            parser=d.get("parser", "unknown"),
            parser_version=d.get("parser_version"),
            model_version=d.get("model_version"),
            screenshot_sha256=d.get("screenshot_sha256"),
            image_width=d.get("image_width"),
            image_height=d.get("image_height"),
            elements=elements,
            error_code=d.get("error_code"),
            message=d.get("message"),
            parse_duration_ms=d.get("parse_duration_ms"),
        )
    
    @classmethod
    def success(
        cls,
        parser: str,
        parser_version: str,
        model_version: str,
        screenshot_sha256: str,
        image_width: int,
        image_height: int,
        elements: List[VisualUIElement],
        parse_duration_ms: float,
    ) -> "VisualUIEvidence":
        return cls(
            status="success",
            parser=parser,
            parser_version=parser_version,
            model_version=model_version,
            screenshot_sha256=screenshot_sha256,
            image_width=image_width,
            image_height=image_height,
            elements=elements,
            parse_duration_ms=parse_duration_ms,
        )
    
    @classmethod
    def failed(cls, parser: str, error_code: str, message: str) -> "VisualUIEvidence":
        return cls(
            status="failed",
            parser=parser,
            error_code=error_code,
            message=message,
        )
    
    @classmethod
    def skipped(cls, parser: str, reason: str) -> "VisualUIEvidence":
        return cls(
            status="skipped",
            parser=parser,
            message=reason,
        )
    
    @classmethod
    def unavailable(cls, parser: str, error_code: str = "OMNIPARSER_NOT_AVAILABLE") -> "VisualUIEvidence":
        return cls(
            status="unavailable",
            parser=parser,
            error_code=error_code,
            message=f"{parser} runtime not available",
        )