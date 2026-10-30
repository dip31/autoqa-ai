"""
Security‑specific data models (in‑memory representations).
These mirror the persistent tables defined in the migration step.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class TargetAuthorization:
    """User‑owned, verified target authorization record."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: int = 0
    hostname: str = ""
    scheme: str = "https"
    port: Optional[int] = None
    path_prefix: str = "/"
    allow_subdomains: bool = False
    verification_method: str = "hosted_file"   # or "dns_txt"
    verification_status: str = "pending"       # pending, verified, failed, revoked
    verification_token: Optional[str] = None
    verified_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    # Active testing fields
    active_testing_allowed: bool = False       # Explicit permission for active testing
    active_testing_scope: Optional[str] = None  # JSON string of additional active scope


@dataclass
class SecurityRun:
    """A security validation run (maps to autonomous_runs with run_type='security')."""
    id: int = 0
    user_id: int = 0
    title: str = ""
    target_url: str = ""
    normalized_target: str = ""
    status: str = "Pending"          # Pending, Running, Completed, Failed, Cancelled, Blocked
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    validators_executed: int = 0
    findings_count: int = 0
    error_summary: str = ""
    policy_version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    # Active testing fields
    mode: str = "passive"              # 'passive' or 'active'
    profile: str = "passive_only"      # Testing profile
    dry_run: bool = False              # Whether this is a dry-run
    confirmed: bool = False            # User confirmation for active mode
    confirmation_token: Optional[str] = None
    confirmation_expires_at: Optional[datetime] = None
    profile_limits: Optional[str] = None  # JSON string of profile-specific limits
    active_authorization_id: Optional[str] = None  # Reference to active authorization
    dry_run_plan: Optional[str] = None   # JSON string of dry-run plan


@dataclass
class SecurityFinding:
    """Individual security finding produced by a validator."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_id: int = 0
    validator_id: str = ""
    finding_type: str = ""
    title: str = ""
    description: str = ""
    severity: str = "Informational"   # Informational, Low, Medium, High, Critical
    confidence: float = 0.5           # 0.0 – 1.0
    affected_url: str = ""
    evidence_refs: List[str] = field(default_factory=list)   # evidence IDs
    recommendation: str = ""
    classification: str = ""         # e.g. "MissingHeader", "InsecureCookie"
    first_seen: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)
    # Active testing fields
    check_type: str = "passive"          # 'passive' or 'active'
    active_check_id: Optional[str] = None  # Reference to active check that generated this
    execution_phase: str = "passive"     # 'passive', 'active', 'dry_run'


@dataclass
class SecurityEvidence:
    """Sanitised evidence supporting a finding."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    finding_id: str = ""
    evidence_type: str = ""          # header, cookie, body_excerpt, tls_info, redirect_chain
    url: str = ""
    method: str = "GET"
    status_code: Optional[int] = None
    # Store only safe, sanitised data
    data: Dict[str, Any] = field(default_factory=dict)
    collected_at: datetime = field(default_factory=datetime.utcnow)
    redacted: bool = True
    # Active testing fields
    check_type: str = "passive"          # 'passive' or 'active'
    active_check_id: Optional[str] = None


@dataclass
class ValidatorResult:
    """Result of a single validator execution."""
    validator_id: str = ""
    validator_name: str = ""
    run_id: int = 0
    status: str = "Completed"        # Completed, Skipped, Failed, Cancelled
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    checks_performed: int = 0
    findings_generated: int = 0
    error: Optional[str] = None
    # Active testing fields
    check_type: str = "passive"          # 'passive' or 'active'
    budget_used: Optional[Dict[str, Any]] = None  # Budget usage snapshot


# ----------------------------------------------------------------------
# Helper: severity ordering
# ----------------------------------------------------------------------
SEVERITY_ORDER = {
    "Informational": 0,
    "Low": 1,
    "Medium": 2,
    "High": 3,
    "Critical": 4,
}


def severity_rank(sev: str) -> int:
    return SEVERITY_ORDER.get(sev, 0)