"""
Vision Module Configuration — Environment-driven settings for visual parsing.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class VisionConfig:
    """
    Configuration for visual UI parsing (Phase 1.5E).
    
    All settings are environment-variable driven with sensible defaults.
    """
    
    # Master enable/disable for visual parsing
    visual_parsing_enabled: bool = True
    
    # OmniParser-specific settings
    omniparser_enabled: bool = True
    
    # OmniParser runtime configuration
    omniparser_runtime: str = "subprocess"  # "subprocess" | "http"
    
    # Timeout for OmniParser inference (milliseconds)
    omniparser_timeout_ms: int = 120000  # 2 minutes default for GPU inference
    
    # OmniParser installation paths (environment variables take precedence)
    omniparser_home: str = field(default_factory=lambda: os.getenv(
        "OMNIPARSER_HOME", 
        str(Path.home() / "omniparser")
    ))
    omniparser_python: str = field(default_factory=lambda: os.getenv(
        "OMNIPARSER_PYTHON", 
        "python"  # Use system python; assumes OmniParser env is activated
    ))
    omniparser_model_dir: str = field(default_factory=lambda: os.getenv(
        "OMNIPARSER_MODEL_DIR",
        str(Path.home() / "omniparser" / "weights")
    ))
    omniparser_command: str = field(default_factory=lambda: os.getenv(
        "OMNIPARSER_COMMAND", 
        ""  # If set, use this command directly instead of python -m
    ))
    
    # OmniParser inference parameters
    omniparser_box_threshold: float = 0.05
    omniparser_iou_threshold: float = 0.1
    omniparser_use_paddleocr: bool = True
    omniparser_imgsz: int = 640
    
    # Cache settings
    cache_enabled: bool = True
    cache_dir: str = field(default_factory=lambda: os.getenv(
        "AGENTQE_VISION_CACHE_DIR",
        str(Path(__file__).resolve().parents[3] / "backend" / "data" / "agentqe" / "vision_cache")
    ))
    
    # Security: screenshot artifact directory (must match crawler config)
    screenshot_artifact_dir: str = field(default_factory=lambda: os.getenv(
        "AGENTQE_SCREENSHOT_DIR",
        str(Path(__file__).resolve().parents[3] / "backend" / "data" / "agentqe" / "screenshots")
    ))
    
    def __post_init__(self):
        # Ensure cache directory exists
        if self.cache_enabled:
            Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        
        # Normalize paths
        self.omniparser_home = str(Path(self.omniparser_home).resolve())
        self.omniparser_model_dir = str(Path(self.omniparser_model_dir).resolve())
        self.screenshot_artifact_dir = str(Path(self.screenshot_artifact_dir).resolve())
        self.cache_dir = str(Path(self.cache_dir).resolve())
    
    @classmethod
    def from_env(cls) -> "VisionConfig":
        """Create config from environment variables."""
        # Only pass env vars that are actually set, to allow default_factory to work
        kwargs = {
            "visual_parsing_enabled": os.getenv("VISUAL_PARSING_ENABLED", "true").lower() == "true",
            "omniparser_enabled": os.getenv("OMNIPARSER_ENABLED", "true").lower() == "true",
            "omniparser_runtime": os.getenv("OMNIPARSER_RUNTIME", "subprocess"),
            "omniparser_timeout_ms": int(os.getenv("OMNIPARSER_TIMEOUT_MS", "120000")),
            "omniparser_python": os.getenv("OMNIPARSER_PYTHON", "python"),
            "omniparser_command": os.getenv("OMNIPARSER_COMMAND", ""),
            "omniparser_box_threshold": float(os.getenv("OMNIPARSER_BOX_THRESHOLD", "0.05")),
            "omniparser_iou_threshold": float(os.getenv("OMNIPARSER_IOU_THRESHOLD", "0.1")),
            "omniparser_use_paddleocr": os.getenv("OMNIPARSER_USE_PADDLEOCR", "true").lower() == "true",
            "omniparser_imgsz": int(os.getenv("OMNIPARSER_IMGSZ", "640")),
            "cache_enabled": os.getenv("VISION_CACHE_ENABLED", "true").lower() == "true",
        }
        
        # Only add path fields if env var is explicitly set
        if "OMNIPARSER_HOME" in os.environ:
            kwargs["omniparser_home"] = os.getenv("OMNIPARSER_HOME")
        if "OMNIPARSER_MODEL_DIR" in os.environ:
            kwargs["omniparser_model_dir"] = os.getenv("OMNIPARSER_MODEL_DIR")
        if "AGENTQE_VISION_CACHE_DIR" in os.environ:
            kwargs["cache_dir"] = os.getenv("AGENTQE_VISION_CACHE_DIR")
        if "AGENTQE_SCREENSHOT_DIR" in os.environ:
            kwargs["screenshot_artifact_dir"] = os.getenv("AGENTQE_SCREENSHOT_DIR")
        
        return cls(**kwargs)
    
    def get_cache_key(self, screenshot_sha256: str, parser_version: str, model_version: str) -> str:
        """Generate a cache key including screenshot hash and parser/model versions."""
        import hashlib
        key_data = f"{screenshot_sha256}|{parser_version}|{model_version}|{self.omniparser_box_threshold}|{self.omniparser_iou_threshold}|{self.omniparser_imgsz}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]


# Global config instance (can be overridden in tests)
_vision_config: Optional[VisionConfig] = None


def get_vision_config() -> VisionConfig:
    """Get the global vision config, creating it if needed."""
    global _vision_config
    if _vision_config is None:
        _vision_config = VisionConfig.from_env()
    return _vision_config


def set_vision_config(config: VisionConfig) -> None:
    """Set the global vision config (primarily for testing)."""
    global _vision_config
    _vision_config = config