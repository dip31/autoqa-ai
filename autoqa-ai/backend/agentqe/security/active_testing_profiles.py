"""
Active Testing Profiles – defines testing profiles for active security assessments.

Profiles define the permissions, limits, and restrictions for different types of
active security assessments. They ensure that active testing is conducted within
safe, well-defined boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from typing import FrozenSet

from agentqe.security.security_config import CONFIG


@dataclass(frozen=True)
class TestingProfile:
    """
    Defines an active testing profile with its permissions and limits.
    
    Profiles are immutable and should be treated as configuration constants.
    """
    # Profile identifier
    id: str
    # Human-readable name
    name: str
    # Description of what this profile permits
    description: str
    # Whether this profile is enabled by default
    enabled: bool = True
    # Whether this profile allows active testing (vs passive only)
    allows_active: bool = False
    # Set of allowed check categories for this profile
    allowed_categories: FrozenSet[str] = field(default_factory=frozenset)
    # Maximum duration in seconds
    max_duration_seconds: int = 300
    # Maximum requests per second
    max_requests_per_second: float = 5.0
    # Maximum response size in bytes
    max_response_size_bytes: int = 10 * 1024 * 1024
    # Maximum number of redirects to follow
    max_redirects: int = 5
    # Maximum number of pages to crawl
    max_pages: int = 20
    # Maximum crawl depth
    max_depth: int = 3
    # Maximum concurrent runs for this profile
    max_concurrent_runs: int = 1
    # Whether this profile requires explicit user confirmation
    requires_confirmation: bool = True
    # Whether dry-run mode is supported
    supports_dry_run: bool = True
    # Additional profile-specific settings
    settings: Dict[str, Any] = field(default_factory=dict)


# Predefined testing profiles for Phase 5A
PROFILES: Dict[str, Any] = {
    'passive_only': {
        'id': 'passive_only',
        'name': 'Passive Only',
        'description': 'Passive security validation only - no active test payloads sent',
        'enabled': True,
        'allows_active': False,
        'allowed_categories': frozenset([
            'https_enforcement',
            'security_headers',
            'cookie_security',
            'information_disclosure',
            'redirect_analysis',
            'tls_configuration',
        ]),
        'max_duration_seconds': 300,
        'max_requests_per_second': 5.0,
        'max_response_size_bytes': 10 * 1024 * 1024,
        'max_redirects': 5,
        'max_pages': 20,
        'max_depth': 3,
        'max_concurrent_runs': 3,
        'requires_confirmation': False,
        'supports_dry_run': True,
        'settings': {},
    },
    'safe_active': {
        'id': 'safe_active',
        'name': 'Safe Active',
        'description': 'Safe active testing with non-destructive checks only',
        'enabled': True,
        'allows_active': True,
        'allowed_categories': frozenset([
            'https_enforcement',
            'security_headers',
            'cookie_security',
            'information_disclosure',
            'redirect_analysis',
            'tls_configuration',
            'safe_active_checks',  # Future: non-destructive active checks
        ]),
        'max_duration_seconds': 300,
        'max_requests_per_second': 3.0,  # More conservative for active
        'max_response_size_bytes': 10 * 1024 * 1024,
        'max_redirects': 5,
        'max_pages': 15,
        'max_depth': 2,
        'max_concurrent_runs': 2,
        'requires_confirmation': True,
        'supports_dry_run': True,
        'settings': {
            'safe_checks_only': True,
            'no_state_changing_operations': True,
        },
    },
    'custom': {
        'id': 'custom',
        'name': 'Custom',
        'description': 'Custom profile with user-defined limits (requires admin approval)',
        'enabled': False,  # Disabled by default, requires admin enablement
        'allows_active': True,
        'allowed_categories': frozenset(),  # User-defined
        'max_duration_seconds': 600,
        'max_requests_per_second': 10.0,
        'max_response_size_bytes': 50 * 1024 * 1024,
        'max_redirects': 10,
        'max_pages': 50,
        'max_depth': 5,
        'max_concurrent_runs': 1,
        'requires_confirmation': True,
        'supports_dry_run': True,
        'settings': {
            'requires_admin_approval': True,
        },
    },
    'zap_baseline': {
        'id': 'zap_baseline',
        'name': 'OWASP ZAP Baseline',
        'description': 'Passive baseline scan using OWASP ZAP (Docker required)',
        'enabled': True,
        'allows_active': False,
        'allowed_categories': frozenset([
            'https_enforcement',
            'security_headers',
            'cookie_security',
            'information_disclosure',
            'redirect_analysis',
            'tls_configuration',
            'zap_passive',
        ]),
        'max_duration_seconds': 600,
        'max_requests_per_second': 2.0,
        'max_response_size_bytes': 20 * 1024 * 1024,
        'max_redirects': 10,
        'max_pages': 30,
        'max_depth': 3,
        'max_concurrent_runs': 1,
        'requires_confirmation': False,
        'supports_dry_run': True,
        'settings': {
            'scanner': 'zap',
        },
    },
}


# Profile registry
class ProfileRegistry:
    """Registry for testing profiles."""
    
    def __init__(self):
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self._load_default_profiles()
    
    def _load_default_profiles(self):
        """Load the default profiles."""
        for profile_id, profile_data in PROFILES.items():
            self._profiles[profile_id] = profile_data
    
    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        """Get a profile by ID."""
        return self._profiles.get(profile_id)
    
    def get_profile_obj(self, profile_id: str) -> Optional[Any]:
        """Get a profile as a TestingProfile object."""
        data = self._profiles.get(profile_id)
        if not data:
            return None
        return TestingProfile(**data)
    
    def list_profiles(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """List all profiles."""
        profiles = list(self._profiles.values())
        if enabled_only:
            profiles = [p for p in profiles if p.get('enabled', False)]
        return profiles
    
    def get_active_profiles(self) -> List[Dict[str, Any]]:
        """Get profiles that allow active testing."""
        return [
            p for p in self._profiles.values()
            if p.get('allows_active', False) and p.get('enabled', False)
        ]
    
    def validate_profile(self, profile_id: str) -> bool:
        """Check if a profile ID is valid and enabled."""
        profile = self._profiles.get(profile_id)
        return profile is not None and profile.get('enabled', False)
    
    def get_profile_limits(self, profile_id: str) -> Dict[str, Any]:
        """Get the effective limits for a profile."""
        profile = self._profiles.get(profile_id)
        if not profile:
            return {}
        
        return {
            'max_duration_seconds': profile.get('max_duration_seconds', CONFIG.max_duration_seconds),
            'max_requests_per_second': profile.get('max_requests_per_second', CONFIG.max_requests_per_second),
            'max_response_size_bytes': profile.get('max_response_size_bytes', CONFIG.max_response_size_bytes),
            'max_redirects': profile.get('max_redirects', CONFIG.max_redirects),
            'max_pages': profile.get('max_pages', CONFIG.max_pages),
            'max_depth': profile.get('max_depth', CONFIG.max_depth),
            'max_concurrent_runs': profile.get('max_concurrent_runs', CONFIG.max_concurrent_runs),
        }
    
    def register_profile(self, profile_data: Dict[str, Any]) -> bool:
        """Register a new profile (admin only)."""
        profile_id = profile_data.get('id')
        if not profile_id:
            return False
        if profile_id in self._profiles:
            return False  # Already exists
        self._profiles[profile_id] = profile_data
        return True
    
    def unregister_profile(self, profile_id: str) -> bool:
        """Unregister a profile (admin only)."""
        if profile_id in PROFILES:  # Cannot remove built-in profiles
            return False
        if profile_id in self._profiles:
            del self._profiles[profile_id]
            return True
        return False


# Global registry instance
_registry = ProfileRegistry()


def get_profile_registry() -> ProfileRegistry:
    """Get the global profile registry."""
    return _registry


def get_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    """Get a profile by ID."""
    return _registry.get_profile(profile_id)


def get_profile_limits(profile_id: str) -> Dict[str, Any]:
    """Get effective limits for a profile."""
    return _registry.get_profile_limits(profile_id)


def validate_profile(profile_id: str) -> bool:
    """Validate a profile ID."""
    return _registry.validate_profile(profile_id)


def list_profiles(enabled_only: bool = True) -> List[Dict[str, Any]]:
    """List all profiles."""
    return _registry.list_profiles(enabled_only)


def get_active_profiles() -> List[Dict[str, Any]]:
    """Get profiles that allow active testing."""
    return _registry.get_active_profiles()