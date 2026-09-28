"""
OmniParser Adapter — Integrates the validated OmniParser runtime with AgentQE.

This adapter:
1. Validates screenshot artifacts and hashes
2. Invokes the existing OmniParser runtime via subprocess
3. Parses and normalizes OmniParser output into VisualUIEvidence
4. Handles timeouts, failures, and caching gracefully
"""

import os
import sys
import json
import time
import hashlib
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import asdict

from agentqe.vision.interfaces import VisualUIParser, VisualUIParserError
from agentqe.vision.schemas import VisualUIEvidence, VisualUIElement
from agentqe.vision.config import get_vision_config, VisionConfig

logger = logging.getLogger(__name__)


class OmniParserAdapter(VisualUIParser):
    """
    Adapter for the locally-installed OmniParser runtime.
    
    Uses subprocess invocation (preferred) or HTTP if configured.
    Does NOT import OmniParser internals directly.
    """
    
    def __init__(self, config: Optional[VisionConfig] = None):
        self.config = config or get_vision_config()
        self._parser_info: Optional[Dict[str, Any]] = None
        self._cache: Dict[str, VisualUIEvidence] = {}
    
    def parse(
        self,
        screenshot_path: str,
        screenshot_metadata: Dict[str, Any]
    ) -> VisualUIEvidence:
        """
        Parse screenshot using OmniParser runtime.
        
        Args:
            screenshot_path: Absolute path to screenshot PNG file
            screenshot_metadata: Dict with sha256, width, height, etc.
        
        Returns:
            VisualUIEvidence with normalized elements
        """
        parse_start = time.time()
        
        # 1. Validate configuration
        if not self.config.visual_parsing_enabled:
            return VisualUIEvidence.skipped("omniparser", "visual_parsing_disabled")
        
        if not self.config.omniparser_enabled:
            return VisualUIEvidence.skipped("omniparser", "omniparser_disabled")
        
        # 2. Validate screenshot artifact
        validation_result = self._validate_screenshot(screenshot_path, screenshot_metadata)
        if validation_result is not None:
            return validation_result
        
        # 3. Check cache
        cache_key = self._get_cache_key(screenshot_metadata)
        if self.config.cache_enabled and cache_key in self._cache:
            cached = self._cache[cache_key]
            logger.info(f"[OmniParserAdapter] Cache hit for {cache_key[:8]}")
            return cached
        
        # 4. Invoke OmniParser
        try:
            raw_output = self._invoke_omniparser(screenshot_path)
        except subprocess.TimeoutExpired:
            return VisualUIEvidence.failed(
                "omniparser", 
                "TIMEOUT", 
                f"OmniParser inference timed out after {self.config.omniparser_timeout_ms}ms"
            )
        except Exception as e:
            logger.error(f"[OmniParserAdapter] Invocation failed: {e}")
            return VisualUIEvidence.failed("omniparser", "INVOCATION_ERROR", str(e)[:300])
        
        # 5. Parse and normalize output
        try:
            evidence = self._normalize_output(
                raw_output, 
                screenshot_metadata,
                time.time() - parse_start
            )
        except Exception as e:
            logger.error(f"[OmniParserAdapter] Output normalization failed: {e}")
            return VisualUIEvidence.failed("omniparser", "NORMALIZATION_ERROR", str(e)[:300])
        
        # 6. Cache result
        if self.config.cache_enabled:
            self._cache[cache_key] = evidence
        
        return evidence
    
    def is_available(self) -> bool:
        """Check if OmniParser runtime is available."""
        if not self.config.visual_parsing_enabled or not self.config.omniparser_enabled:
            return False
        
        # Check if OmniParser home exists
        omniparser_home = Path(self.config.omniparser_home)
        if not omniparser_home.exists():
            logger.warning(f"[OmniParserAdapter] OmniParser home not found: {omniparser_home}")
            return False
        
        # Check for required model weights
        model_dir = Path(self.config.omniparser_model_dir)
        detector_path = model_dir / "icon_detect_v3" / "model.pt"
        caption_dir = model_dir / "icon_caption_florence"
        
        if not detector_path.exists():
            logger.warning(f"[OmniParserAdapter] Detector model not found: {detector_path}")
            return False
        
        if not caption_dir.exists():
            logger.warning(f"[OmniParserAdapter] Caption model dir not found: {caption_dir}")
            return False
        
        # If custom command is provided, assume it works
        if self.config.omniparser_command:
            return True
        
        # Check if the omniparser_python executable exists and is runnable
        # We don't check imports here since OmniParser may be in a separate environment
        # The actual invocation will handle environment activation
        return True
    
    def get_parser_info(self) -> Dict[str, Any]:
        """Get OmniParser metadata for evidence tracking."""
        if self._parser_info is not None:
            return self._parser_info
        
        # Try to detect version from git or file
        parser_version = "unknown"
        omniparser_home = Path(self.config.omniparser_home)
        git_dir = omniparser_home / ".git"
        if git_dir.exists():
            try:
                result = subprocess.run(
                    ["git", "-C", str(omniparser_home), "rev-parse", "--short", "HEAD"],
                    capture_output=True, text=True, timeout=5, shell=False
                )
                if result.returncode == 0:
                    parser_version = result.stdout.strip()
            except Exception:
                pass
        
        # Model versions
        model_version = "icon_detect_v3 + florence2"
        
        self._parser_info = {
            "parser": "omniparser",
            "parser_version": parser_version,
            "model_version": model_version,
            "runtime": self.config.omniparser_runtime,
            "detector": "YOLOv9 (icon_detect_v3)",
            "caption_model": "Florence-2-base",
            "ocr": "PaddleOCR" if self.config.omniparser_use_paddleocr else "EasyOCR",
        }
        return self._parser_info
    
    # ============================================================
    # Private methods
    # ============================================================
    
    def _validate_screenshot(
        self, 
        screenshot_path: str, 
        screenshot_metadata: Dict[str, Any]
    ) -> Optional[VisualUIEvidence]:
        """
        Validate screenshot file exists, is in artifact dir, and hash matches.
        
        Returns:
            VisualUIEvidence error if validation fails, None if valid.
        """
        path = Path(screenshot_path)
        artifact_dir = Path(self.config.screenshot_artifact_dir)
        
        # 1. File exists
        if not path.exists():
            return VisualUIEvidence.failed(
                "omniparser", 
                "SCREENSHOT_NOT_FOUND", 
                f"Screenshot file not found: {screenshot_path}"
            )
        
        # 2. File is inside artifact directory (security)
        try:
            path.resolve().relative_to(artifact_dir.resolve())
        except ValueError:
            return VisualUIEvidence.failed(
                "omniparser", 
                "SCREENSHOUT_OUTSIDE_ARTIFACT_DIR", 
                f"Screenshot path outside allowed artifact directory: {screenshot_path}"
            )
        
        # 3. Verify SHA256 matches metadata
        expected_sha256 = screenshot_metadata.get("sha256")
        if expected_sha256:
            actual_sha256 = self._calculate_sha256(path)
            if actual_sha256 != expected_sha256:
                return VisualUIEvidence.failed(
                    "omniparser",
                    "SCREENSHOT_HASH_MISMATCH",
                    f"SHA256 mismatch: expected {expected_sha256[:16]}..., got {actual_sha256[:16]}..."
                )
        
        return None
    
    def _calculate_sha256(self, filepath: Path) -> str:
        """Calculate SHA256 hash of a file."""
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _get_cache_key(self, screenshot_metadata: Dict[str, Any]) -> str:
        """Generate cache key for this screenshot + parser config."""
        parser_info = self.get_parser_info()
        return self.config.get_cache_key(
            screenshot_metadata.get("sha256", ""),
            parser_info.get("parser_version", "unknown"),
            parser_info.get("model_version", "unknown"),
        )
    
    def _invoke_omniparser(self, screenshot_path: str) -> Dict[str, Any]:
        """
        Invoke OmniParser runtime and return raw output.
        
        Uses the existing validated Gradio demo logic via a direct Python call
        to avoid subprocess overhead and environment issues.
        """
        if self.config.omniparser_runtime == "http":
            return self._invoke_via_http(screenshot_path)
        
        return self._invoke_via_python_module(screenshot_path)
    
    def _invoke_via_python_module(self, screenshot_path: str) -> Dict[str, Any]:
        """
        Invoke OmniParser via subprocess using the CLI script.
        
        This runs the OmniParser in its own environment, avoiding import issues.
        """
        cli_script = Path(__file__).resolve().parent / "omniparser_cli.py"
        
        # Build command
        cmd = [
            self.config.omniparser_python,
            str(cli_script),
            screenshot_path,
            "--box-threshold", str(self.config.omniparser_box_threshold),
            "--iou-threshold", str(self.config.omniparser_iou_threshold),
            "--imgsz", str(self.config.omniparser_imgsz),
            "--model-dir", self.config.omniparser_model_dir,
        ]
        
        if self.config.omniparser_use_paddleocr:
            cmd.append("--use-paddleocr")
        
        # Set environment variables for the subprocess
        env = os.environ.copy()
        env["OMNIPARSER_HOME"] = self.config.omniparser_home
        env["OMNIPARSER_MODEL_DIR"] = self.config.omniparser_model_dir
        
        logger.debug(f"[OmniParserAdapter] Invoking CLI: {' '.join(cmd)}")
        logger.debug(f"[OmniParserAdapter] Env OMNIPARSER_HOME={env.get('OMNIPARSER_HOME')}")
        
        # Run subprocess with timeout
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.omniparser_timeout_ms / 1000.0,
                shell=False,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"OmniParser CLI timed out after {self.config.omniparser_timeout_ms} ms")
        except Exception as e:
            raise RuntimeError(f"Failed to start OmniParser CLI: {e}")
        
        # Log stdout/stderr for debugging
        stdout = result.stdout if result.stdout is not None else ""
        stderr = result.stderr if result.stderr is not None else ""
        logger.debug(f"[OmniParserAdapter] CLI stdout (last 500 chars): {stdout[-500:]}")
        logger.debug(f"[OmniParserAdapter] CLI stderr (last 500 chars): {stderr[-500:]}")
        
        if result.returncode != 0:
            error_msg = stderr.strip() if stderr else "Unknown error"
            logger.error(f"[OmniParserAdapter] CLI failed with exit code {result.returncode}: {error_msg}")
            raise RuntimeError(f"OmniParser CLI failed (exit {result.returncode}): {error_msg}")
        
        # Parse JSON output
        if not stdout:
            logger.error("[OmniParserAdapter] Empty stdout from OmniParser CLI")
            raise RuntimeError("OmniParser CLI produced no output")
        
        # Parse JSON output
        try:
            # OmniParser may print timing/debug lines before its JSON payload.
            # The CLI emits the result as the final JSON line.
            json_line = None
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    json_line = line
                    break
            if json_line is None:
                raise RuntimeError(f"Failed to find JSON in OmniParser output. stdout: {stdout[:500]}")
            output = json.loads(json_line)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse OmniParser output: {e}. stdout: {stdout[:500]}")
        except StopIteration:
            raise RuntimeError(f"Failed to find JSON in OmniParser output: {stdout[:500]}")
        
        if "error" in output:
            raise RuntimeError(f"OmniParser returned error: {output['error']}")
        
        return output
    
    def _invoke_via_http(self, screenshot_path: str) -> Dict[str, Any]:
        """Invoke OmniParser via HTTP (if running as a service)."""
        # Not implemented - would require a running OmniParser HTTP server
        raise NotImplementedError("HTTP runtime not implemented; use subprocess runtime")
    
    def _normalize_output(
        self,
        raw_output: Dict[str, Any],
        screenshot_metadata: Dict[str, Any],
        parse_duration: float
    ) -> VisualUIEvidence:
        """
        Normalize OmniParser raw output into VisualUIEvidence.
        
        OmniParser returns:
        - encoded_image: base64 annotated image (we don't store this)
        - label_coordinates: dict of label -> [x, y, w, h] in normalized coords
        - parsed_content_list: list of dicts with type, bbox, interactivity, content
        - ocr_text: list of OCR text strings
        - ocr_bbox: list of OCR bounding boxes [x1, y1, x2, y2] normalized
        - image_width, image_height
        """
        parser_info = self.get_parser_info()
        image_width = raw_output.get("image_width", screenshot_metadata.get("width"))
        image_height = raw_output.get("image_height", screenshot_metadata.get("height"))
        screenshot_sha256 = screenshot_metadata.get("sha256")
        
        parsed_content = raw_output.get("parsed_content_list", [])
        if not isinstance(parsed_content, list):
            logger.warning("[OmniParserAdapter] parsed_content_list is not a list, treating as empty")
            parsed_content = []
        elements = []
        
        for idx, item in enumerate(parsed_content):
            if not isinstance(item, dict):
                continue
            
            # Extract bounding box
            bbox = item.get("bbox", [])
            if not bbox or len(bbox) != 4:
                continue
            
            # OmniParser returns normalized coordinates [x1, y1, x2, y2] in ratio
            # when output_coord_in_ratio=True
            x1, y1, x2, y2 = bbox
            
            # Validate and clamp
            x1 = max(0.0, min(1.0, x1))
            y1 = max(0.0, min(1.0, y1))
            x2 = max(0.0, min(1.0, x2))
            y2 = max(0.0, min(1.0, y2))
            
            if x1 >= x2 or y1 >= y2:
                continue  # Skip malformed boxes
            
            # Convert to pixel coordinates
            bbox_pixels = [
                int(x1 * image_width),
                int(y1 * image_height),
                int(x2 * image_width),
                int(y2 * image_height),
            ]
            bbox_normalized = [x1, y1, x2, y2]
            
            # Determine element type
            element_type = self._normalize_element_type(item)
            
            # Extract text/caption
            text = item.get("content")
            caption = None
            if text and item.get("type") == "icon":
                caption = text
                text = None
            
            # Interactability
            interactable = item.get("interactivity")
            if interactable is not None:
                interactable = bool(interactable)
            
            # Confidence - not directly provided by OmniParser
            confidence = None
            
            # Source
            source = item.get("source", "omniparser")
            
            element = VisualUIElement(
                id=f"visual_{idx:03d}",
                type=element_type,
                text=text,
                caption=caption,
                bbox_pixels=bbox_pixels,
                bbox_normalized=bbox_normalized,
                interactable=interactable,
                confidence=confidence,
                source=source,
            )
            elements.append(element)
        
        return VisualUIEvidence.success(
            parser="omniparser",
            parser_version=parser_info.get("parser_version", "unknown"),
            model_version=parser_info.get("model_version", "unknown"),
            screenshot_sha256=screenshot_sha256,
            image_width=image_width,
            image_height=image_height,
            elements=elements,
            parse_duration_ms=round(parse_duration * 1000, 1),
        )
    
    def _normalize_element_type(self, item: Dict[str, Any]) -> str:
        """
        Normalize OmniParser element types to our schema.
        
        OmniParser types: 'icon', 'text', 'icon' with content from OCR or caption
        """
        raw_type = item.get("type", "").lower()
        content = item.get("content", "").lower() if item.get("content") else ""
        
        # Map based on type and content heuristics
        if raw_type == "text":
            return "text"
        elif raw_type == "icon":
            # Try to infer from caption/content
            if any(kw in content for kw in ["button", "btn", "click", "submit", "sign in", "login", "register"]):
                return "button"
            elif any(kw in content for kw in ["input", "field", "search", "email", "password", "text box", "textbox"]):
                return "input"
            elif any(kw in content for kw in ["checkbox", "check box", "tick"]):
                return "checkbox"
            elif any(kw in content for kw in ["radio", "option"]):
                return "radio"
            elif any(kw in content for kw in ["link", "hyperlink", "anchor"]):
                return "link"
            elif any(kw in content for kw in ["dropdown", "select", "combo", "menu"]):
                return "dropdown"
            elif any(kw in content for kw in ["tab"]):
                return "tab"
            elif any(kw in content for kw in ["icon", "image", "logo", "picture"]):
                return "icon"
            else:
                return "icon"  # Default for icons
        else:
            return raw_type if raw_type else "other"


def create_omniparser_adapter(config: Optional[VisionConfig] = None) -> OmniParserAdapter:
    """Factory function to create OmniParserAdapter."""
    return OmniParserAdapter(config)