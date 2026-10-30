"""
Finding Lifecycle Management – manages the complete lifecycle of security findings.

This module provides:
- Lifecycle state machine with validated transitions
- Remediation lifecycle tracking
- Finding history persistence
- Resolution and resolution workflows
- Audit trail for all finding lifecycle events
"""

from __future__ import annotations

import logging
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager

from database.db import execute_query, DB_PATH
from agentqe.security.finding_verifier import VerificationState

logger = logging.getLogger(__name__)


class ExecutionOutcome(Enum):
    """Execution outcome of a security check."""
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"
    BLOCKED = "blocked"
    ERROR = "error"
    NOT_ASSESSED = "not_assessed"


class VerificationState(Enum):
    """Verification state of a finding."""
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    INCONCLUSIVE = "inconclusive"
    REJECTED = "rejected"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


class LifecycleState(Enum):
    """Remediation lifecycle state of a finding."""
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_REMEDIATION = "in_remediation"
    RESOLVED = "resolved"
    REOPENED = "reopened"
    ACCEPTED_RISK = "accepted_risk"


class ResolutionType(Enum):
    """Type of resolution for a finding."""
    VERIFIED_REMEDIATION = "verified_remediation"
    MANUAL_RESOLUTION = "manual_resolution"
    FALSE_POSITIVE_REJECTION = "false_positive_rejection"
    ACCEPTED_RISK = "accepted_risk"


class LifecycleTransition(Enum):
    """Allowed lifecycle transitions."""
    OPEN_TO_ACKNOWLEDGED = "open_to_acknowledged"
    OPEN_TO_IN_REMEDIATION = "open_to_in_remediation"
    ACKNOWLEDGED_TO_IN_REMEDIATION = "acknowledged_to_in_remediation"
    IN_REMEDIATION_TO_RESOLVED = "in_remediation_to_resolved"
    RESOLVED_TO_REOPENED = "resolved_to_reopened"
    OPEN_TO_ACCEPTED_RISK = "open_to_accepted_risk"
    ACKNOWLEDGED_TO_ACCEPTED_RISK = "acknowledged_to_accepted_risk"
    IN_REMEDIATION_TO_ACCEPTED_RISK = "in_remediation_to_accepted_risk"
    ACCEPTED_RISK_TO_REOPENED = "accepted_risk_to_reopened"
    REOPENED_TO_IN_REMEDIATION = "reopened_to_in_remediation"


# Valid transitions: (from_state, to_state) -> allowed
VALID_TRANSITIONS: Dict[LifecycleState, Set[LifecycleState]] = {
    LifecycleState.OPEN: {
        LifecycleState.ACKNOWLEDGED,
        LifecycleState.IN_REMEDIATION,
        LifecycleState.ACCEPTED_RISK,
    },
    LifecycleState.ACKNOWLEDGED: {
        LifecycleState.IN_REMEDIATION,
        LifecycleState.ACCEPTED_RISK,
    },
    LifecycleState.IN_REMEDIATION: {
        LifecycleState.RESOLVED,
        LifecycleState.ACCEPTED_RISK,
    },
    LifecycleState.RESOLVED: {
        LifecycleState.REOPENED,
    },
    LifecycleState.REOPENED: {
        LifecycleState.IN_REMEDIATION,
    },
    LifecycleState.ACCEPTED_RISK: {
        LifecycleState.REOPENED,
    },
}

# Valid resolution types for each transition
VALID_RESOLUTION_TYPES: Dict[Tuple[LifecycleState, LifecycleState], Set[ResolutionType]] = {
    (LifecycleState.IN_REMEDIATION, LifecycleState.RESOLVED): {
        ResolutionType.VERIFIED_REMEDIATION,
        ResolutionType.MANUAL_RESOLUTION,
    },
    (LifecycleState.OPEN, LifecycleState.ACCEPTED_RISK): {
        ResolutionType.ACCEPTED_RISK,
    },
    (LifecycleState.ACKNOWLEDGED, LifecycleState.ACCEPTED_RISK): {
        ResolutionType.ACCEPTED_RISK,
    },
    (LifecycleState.IN_REMEDIATION, LifecycleState.ACCEPTED_RISK): {
        ResolutionType.ACCEPTED_RISK,
    },
    (LifecycleState.OPEN, LifecycleState.ACCEPTED_RISK): {
        ResolutionType.ACCEPTED_RISK,
    },
    (LifecycleState.RESOLVED, LifecycleState.REOPENED): {
        ResolutionType.MANUAL_RESOLUTION,
    },
    (LifecycleState.REOPENED, LifecycleState.IN_REMEDIATION): {
        ResolutionType.MANUAL_RESOLUTION,
    },
}

# Resolution types that don't require verified remediation
MANUAL_RESOLUTION_TYPES = {
    ResolutionType.MANUAL_RESOLUTION,
    ResolutionType.FALSE_POSITIVE_REJECTION,
    ResolutionType.ACCEPTED_RISK,
}


@dataclass(frozen=True)
class LifecycleEvent:
    """Immutable record of a lifecycle event."""
    event_id: str
    finding_id: int
    run_id: Optional[int]
    event_type: str  # created, evidence_added, verification_updated, severity_changed, confidence_changed, acknowledged, remediation_started, resolved, reopened, risk_accepted, deduplicated, manual_review_requested
    previous_lifecycle_state: Optional[LifecycleState]
    new_lifecycle_state: Optional[LifecycleState]
    previous_verification_state: Optional[str]
    new_verification_state: Optional[str]
    actor_id: Optional[int]
    actor_name: Optional[str]
    reason: str
    evidence_refs: List[str] = field(default_factory=list)
    execution_ref: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "finding_id": self.finding_id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "previous_lifecycle_state": self.previous_lifecycle_state.value if self.previous_lifecycle_state else None,
            "new_lifecycle_state": self.new_lifecycle_state.value if self.new_lifecycle_state else None,
            "previous_verification_state": self.previous_verification_state,
            "new_verification_state": self.new_verification_state,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "reason": self.reason,
            "evidence_refs": self.evidence_refs,
            "execution_ref": self.execution_ref,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class FindingLifecycle:
    """Mutable lifecycle state for a finding."""
    finding_id: int
    lifecycle_state: LifecycleState = LifecycleState.OPEN
    verification_state: VerificationState = VerificationState.CANDIDATE
    severity: str = "Informational"
    confidence: float = 0.5
    resolution_type: Optional[ResolutionType] = None
    resolution_reason: Optional[str] = None
    resolution_evidence_refs: List[str] = field(default_factory=list)
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[int] = None
    remediation_started_at: Optional[datetime] = None
    remediation_started_by: Optional[int] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None
    accepted_risk_at: Optional[datetime] = None
    accepted_risk_by: Optional[int] = None
    risk_acceptance_reason: Optional[str] = None
    reopened_count: int = 0
    last_verification_at: Optional[datetime] = None
    verification_state: VerificationState = VerificationState.CANDIDATE
    verification_confidence: float = 0.5
    version: int = 1  # For optimistic locking


class FindingLifecycleManager:
    """
    Manages the complete lifecycle of security findings.
    
    Handles:
    - Lifecycle state transitions with validation
    - Finding history persistence
    - Verification state integration
    - Resolution workflows
    - Audit trail
    """
    
    def __init__(self):
        self._init_tables()
    
    def _init_tables(self):
        """Initialize database tables for finding lifecycle."""
        execute_query("""
            CREATE TABLE IF NOT EXISTS security_finding_lifecycle (
                finding_id INTEGER PRIMARY KEY,
                lifecycle_state TEXT NOT NULL DEFAULT 'open',
                verification_state TEXT NOT NULL DEFAULT 'candidate',
                severity TEXT NOT NULL DEFAULT 'Informational',
                confidence REAL NOT NULL DEFAULT 0.5,
                resolution_type TEXT,
                resolution_reason TEXT,
                resolution_evidence_refs TEXT,
                resolved_at TIMESTAMP,
                resolved_by INTEGER,
                acknowledged_at TIMESTAMP,
                acknowledged_by INTEGER,
                remediation_started_at TIMESTAMP,
                remediation_started_by INTEGER,
                resolved_at TIMESTAMP,
                resolved_by INTEGER,
                accepted_risk_at TIMESTAMP,
                accepted_risk_by INTEGER,
                risk_acceptance_reason TEXT,
                reopened_count INTEGER DEFAULT 0,
                last_verification_at TIMESTAMP,
                verification_state TEXT NOT NULL DEFAULT 'candidate',
                verification_confidence REAL DEFAULT 0.5,
                version INTEGER NOT NULL DEFAULT 1,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (finding_id) REFERENCES security_findings(id) ON DELETE CASCADE
            )
        """)
        
        execute_query("""
            CREATE TABLE IF NOT EXISTS security_finding_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                finding_id INTEGER NOT NULL,
                run_id INTEGER,
                event_type TEXT NOT NULL,
                previous_lifecycle_state TEXT,
                new_lifecycle_state TEXT,
                previous_verification_state TEXT,
                new_verification_state TEXT,
                actor_id INTEGER,
                actor_name TEXT,
                reason TEXT,
                evidence_refs TEXT,
                execution_ref TEXT,
                metadata TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (finding_id) REFERENCES security_findings(id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes
        execute_query("CREATE INDEX IF NOT EXISTS idx_finding_history_finding_id ON security_finding_history(finding_id)")
        execute_query("CREATE INDEX IF NOT EXISTS idx_finding_history_run_id ON security_finding_history(run_id)")
        execute_query("CREATE INDEX IF NOT EXISTS idx_finding_history_timestamp ON security_finding_history(timestamp)")
        execute_query("CREATE INDEX IF NOT EXISTS idx_finding_lifecycle_finding_id ON security_finding_lifecycle(finding_id)")
    
    def _get_lifecycle(self, finding_id: int) -> Optional[FindingLifecycle]:
        """Get lifecycle state for a finding."""
        rows = execute_query(
            "SELECT * FROM security_finding_lifecycle WHERE finding_id = ?",
            (finding_id,), fetch=True
        )
        if not rows:
            return None
        
        row = rows[0]
        return FindingLifecycle(
            finding_id=row["finding_id"],
            lifecycle_state=LifecycleState(row["lifecycle_state"]),
            verification_state=VerificationState(row["verification_state"]),
            severity=row["severity"],
            confidence=row["confidence"],
            resolution_type=ResolutionType(row["resolution_type"]) if row["resolution_type"] else None,
            resolution_reason=row["resolution_reason"],
            resolution_evidence_refs=json.loads(row["resolution_evidence_refs"]) if row["resolution_evidence_refs"] else [],
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            resolved_by=row["resolved_by"],
            acknowledged_at=datetime.fromisoformat(row["acknowledged_at"]) if row["acknowledged_at"] else None,
            acknowledged_by=row["acknowledged_by"],
            remediation_started_at=datetime.fromisoformat(row["remediation_started_at"]) if row["remediation_started_at"] else None,
            remediation_started_by=row["remediation_started_by"],
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            resolved_by=row["resolved_by"],
            accepted_risk_at=datetime.fromisoformat(row["accepted_risk_at"]) if row["accepted_risk_at"] else None,
            accepted_risk_by=row["accepted_risk_by"],
            risk_acceptance_reason=row["risk_acceptance_reason"],
            reopened_count=row["reopened_count"] or 0,
            last_verification_at=datetime.fromisoformat(row["last_verification_at"]) if row["last_verification_at"] else None,
            verification_state=VerificationState(row["verification_state"]),
            verification_confidence=row["verification_confidence"],
            version=row["version"] or 1,
        )
    
    def _save_lifecycle(self, lifecycle: FindingLifecycle) -> bool:
        """Save lifecycle state to database."""
        query = """
            INSERT OR REPLACE INTO security_finding_lifecycle (
                finding_id, lifecycle_state, verification_state, severity, confidence,
                resolution_type, resolution_reason, resolution_evidence_refs,
                resolved_at, resolved_by, acknowledged_at, acknowledged_by,
                remediation_started_at, remediation_started_by, resolved_at,
                resolved_by, accepted_risk_at, accepted_risk_by,
                risk_acceptance_reason, reopened_count,
                last_verification_at, verification_state, verification_confidence,
                version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            execute_query(query, (
                lifecycle.finding_id,
                lifecycle.lifecycle_state.value,
                lifecycle.verification_state.value,
                lifecycle.severity,
                lifecycle.confidence,
                lifecycle.resolution_type.value if lifecycle.resolution_type else None,
                lifecycle.resolution_reason,
                json.dumps(lifecycle.resolution_evidence_refs),
                lifecycle.resolved_at.isoformat() if lifecycle.resolved_at else None,
                lifecycle.resolved_by,
                lifecycle.acknowledged_at.isoformat() if lifecycle.acknowledged_at else None,
                lifecycle.acknowledged_by,
                lifecycle.remediation_started_at.isoformat() if lifecycle.remediation_started_at else None,
                lifecycle.remediation_started_by,
                lifecycle.resolved_at.isoformat() if lifecycle.resolved_at else None,
                lifecycle.resolved_by,
                lifecycle.accepted_risk_at.isoformat() if lifecycle.accepted_risk_at else None,
                lifecycle.accepted_risk_by,
                lifecycle.risk_acceptance_reason,
                lifecycle.reopened_count,
                lifecycle.last_verification_at.isoformat() if lifecycle.last_verification_at else None,
                lifecycle.verification_state.value,
                lifecycle.verification_confidence,
                lifecycle.version,
                datetime.utcnow().isoformat(),
            ))
            return True
        except Exception as e:
            logger.error(f"Failed to save lifecycle for finding {lifecycle.finding_id}: {e}")
            return False
    
    def _record_history(self, event: LifecycleEvent) -> bool:
        """Record a lifecycle event in the history table."""
        try:
            execute_query(
                """INSERT INTO security_finding_history 
                   (event_id, finding_id, run_id, event_type, previous_lifecycle_state,
                    new_lifecycle_state, previous_verification_state, new_verification_state,
                    actor_id, actor_name, reason, evidence_refs, execution_ref, metadata, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.finding_id,
                    event.run_id,
                    event.event_type,
                    event.previous_lifecycle_state.value if event.previous_lifecycle_state else None,
                    event.new_lifecycle_state.value if event.new_lifecycle_state else None,
                    event.previous_verification_state,
                    event.new_verification_state,
                    event.actor_id,
                    event.actor_name,
                    event.reason,
                    json.dumps(event.evidence_refs),
                    event.execution_ref,
                    json.dumps(event.metadata),
                    event.timestamp.isoformat(),
                ))
            return True
        except Exception as e:
            logger.error(f"Failed to record history for finding {event.finding_id}: {e}")
            return False
    
    def transition_lifecycle(
        self,
        finding_id: int,
        new_lifecycle_state: LifecycleState,
        actor_id: int,
        actor_name: str,
        reason: str,
        evidence_refs: List[str] = None,
        execution_ref: Optional[str] = None,
        metadata: Dict[str, Any] = None,
        resolution_type: Optional[ResolutionType] = None,
        resolution_reason: Optional[str] = None,
        resolution_evidence_refs: List[str] = None,
        expected_version: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Transition a finding to a new lifecycle state.
        
        Returns (success, message). If success is False, message contains error reason.
        """
        # Get current lifecycle
        current = self._get_lifecycle(finding_id)
        if not current:
            # Create initial lifecycle for new finding
            current = FindingLifecycle(finding_id=finding_id)
            if not self._save_lifecycle(current):
                return False, "Failed to create initial lifecycle"
        
        # Check version for optimistic locking
        if expected_version is not None and current.version != expected_version:
            return False, f"Version conflict: expected version {expected_version}, current is {current.version}"
        
        # Validate transition
        if not self._is_valid_transition(current.lifecycle_state, new_lifecycle_state):
            return False, f"Invalid transition from {current.lifecycle_state.value} to {new_lifecycle_state.value}"
        
        # Validate resolution requirements
        if new_lifecycle_state == LifecycleState.RESOLVED:
            if not resolution_type:
                return False, "Resolution type required when resolving a finding"
            if resolution_type not in VALID_RESOLUTION_TYPES.get((LifecycleState.IN_REMEDIATION, LifecycleState.RESOLVED), set()):
                return False, f"Invalid resolution type {resolution_type.value} for transition from in_remediation to resolved"
            if not resolution_reason:
                return False, "Resolution reason required when resolving a finding"
        
        if new_lifecycle_state == LifecycleState.ACCEPTED_RISK:
            if not resolution_type or resolution_type != ResolutionType.ACCEPTED_RISK:
                return False, "Risk acceptance requires resolution_type=accepted_risk"
            if not resolution_reason:
                return False, "Risk acceptance reason required"
        
        if new_lifecycle_state == LifecycleState.REOPENED:
            # Check if recurrence criteria are met (would need additional evidence)
            if not metadata or not metadata.get("recurrence_evidence"):
                return False, "Reopening requires recurrence evidence in metadata"
        
        # Store previous states for history
        previous_lifecycle_state = current.lifecycle_state
        previous_verification_state = current.verification_state.value
        
        # Perform transition
        now = datetime.utcnow()
        current.lifecycle_state = new_lifecycle_state
        current.version += 1
        
        # Update timestamps and actors based on new state
        if new_lifecycle_state == LifecycleState.ACKNOWLEDGED:
            current.acknowledged_at = datetime.utcnow()
            current.acknowledged_by = actor_id
        elif new_lifecycle_state == LifecycleState.IN_REMEDIATION:
            current.remediation_started_at = now
            current.remediation_started_by = actor_id
        elif new_lifecycle_state == LifecycleState.RESOLVED:
            current.resolved_at = now
            current.resolved_by = actor_id
            current.resolution_type = resolution_type
            current.resolution_reason = resolution_reason
            current.resolution_evidence_refs = resolution_evidence_refs or []
        elif new_lifecycle_state == LifecycleState.ACCEPTED_RISK:
            current.accepted_risk_at = now
            current.accepted_risk_by = actor_id
            current.risk_acceptance_reason = resolution_reason
        elif new_lifecycle_state == LifecycleState.REOPENED:
            current.reopened_count += 1
            current.resolved_at = None
            current.resolved_by = None
            current.resolution_type = None
            current.resolution_reason = None
            current.resolution_evidence_refs = []
        
        # Update verification state if provided in metadata
        if metadata and "verification_state" in metadata:
            try:
                new_verification_state = VerificationState(metadata["verification_state"])
                current.verification_state = new_verification_state
                current.last_verification_at = datetime.utcnow()
                if "verification_confidence" in metadata:
                    current.verification_confidence = metadata["verification_confidence"]
            except ValueError:
                pass
        
        # Save lifecycle
        if not self._save_lifecycle(current):
            return False, "Failed to save lifecycle state"
        
        # Record history
        event = LifecycleEvent(
            event_id=f"evt_{uuid.uuid4().hex[:16]}",
            finding_id=finding_id,
            run_id=metadata.get("run_id") if metadata else None,
            event_type=self._get_event_type(current.lifecycle_state, new_lifecycle_state),
            previous_lifecycle_state=previous_lifecycle_state,
            new_lifecycle_state=new_lifecycle_state,
            previous_verification_state=previous_verification_state,
            new_verification_state=current.verification_state.value,
            actor_id=actor_id,
            actor_name=actor_name,
            reason=reason,
            evidence_refs=evidence_refs or [],
            execution_ref=execution_ref,
            metadata=metadata or {},
        )
        self._record_history(event)
        
        logger.info(f"Finding {finding_id} transitioned from {previous_lifecycle_state.value} to {new_lifecycle_state.value}")
        return True, "Transition successful"
    
    def _is_valid_transition(self, from_state: LifecycleState, to_state: LifecycleState) -> bool:
        """Check if a lifecycle transition is valid."""
        valid_transitions = VALID_TRANSITIONS.get(from_state, set())
        return to_state in valid_transitions
    
    def _get_event_type(self, from_state: LifecycleState, to_state: LifecycleState) -> str:
        """Determine event type from state transition."""
        if to_state == LifecycleState.ACKNOWLEDGED:
            return "acknowledged"
        elif to_state == LifecycleState.IN_REMEDIATION:
            return "remediation_started"
        elif to_state == LifecycleState.RESOLVED:
            return "resolved"
        elif to_state == LifecycleState.REOPENED:
            return "reopened"
        elif to_state == LifecycleState.ACCEPTED_RISK:
            return "risk_accepted"
        elif to_state == LifecycleState.OPEN:
            return "reopened"
        return "lifecycle_changed"
    
    def acknowledge_finding(
        self,
        finding_id: int,
        actor_id: int,
        actor_name: str,
        reason: str,
        evidence_refs: List[str] = None,
    ) -> Tuple[bool, str]:
        """Acknowledge a finding."""
        return self.transition_lifecycle(
            finding_id, LifecycleState.ACKNOWLEDGED, actor_id, actor_name, reason,
            evidence_refs=evidence_refs
        )
    
    def start_remediation(
        self,
        finding_id: int,
        actor_id: int,
        actor_name: str,
        reason: str,
        evidence_refs: List[str] = None,
    ) -> Tuple[bool, str]:
        """Start remediation for a finding."""
        return self.transition_lifecycle(
            finding_id, LifecycleState.IN_REMEDIATION, actor_id, actor_name, reason,
            evidence_refs=evidence_refs
        )
    
    def resolve_finding(
        self,
        finding_id: int,
        actor_id: int,
        actor_name: str,
        reason: str,
        resolution_type: ResolutionType,
        resolution_evidence_refs: List[str] = None,
        expected_version: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Resolve a finding with verified remediation or manual resolution."""
        if resolution_type not in {ResolutionType.VERIFIED_REMEDIATION, ResolutionType.MANUAL_RESOLUTION, ResolutionType.FALSE_POSITIVE_REJECTION}:
            return False, f"Invalid resolution type: {resolution_type.value}"
        
        if resolution_type in {ResolutionType.VERIFIED_REMEDIATION, ResolutionType.MANUAL_RESOLUTION} and not resolution_type:
            return False, "Resolution reason required"
        
        return self.transition_lifecycle(
            finding_id, LifecycleState.RESOLVED, actor_id, actor_name, reason,
            resolution_type=resolution_type,
            resolution_reason=reason,
            resolution_evidence_refs=resolution_evidence_refs,
            expected_version=expected_version,
        )
    
    def accept_risk(
        self,
        finding_id: int,
        actor_id: int,
        actor_name: str,
        reason: str,
        expected_version: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Accept risk for a finding."""
        return self.transition_lifecycle(
            finding_id, LifecycleState.ACCEPTED_RISK, actor_id, actor_name, reason,
            resolution_type=ResolutionType.ACCEPTED_RISK,
            resolution_reason=reason,
            expected_version=expected_version,
        )
    
    def reopen_finding(
        self,
        finding_id: int,
        actor_id: int,
        actor_name: str,
        reason: str,
        recurrence_evidence: List[str],
        expected_version: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Reopen a resolved finding with evidence of recurrence."""
        metadata = {"recurrence_evidence": recurrence_evidence}
        return self.transition_lifecycle(
            finding_id, LifecycleState.REOPENED, actor_id, actor_name, reason,
            metadata=metadata, expected_version=expected_version
        )
    
    def request_reverification(
        self,
        finding_id: int,
        actor_id: int,
        actor_name: str,
        reason: str,
        new_verification_state: VerificationState,
        verification_confidence: float,
        expected_version: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Request reverification of a finding."""
        current = self._get_lifecycle(finding_id)
        if not current:
            return False, "Finding lifecycle not found"
        
        if expected_version is not None and current.version != expected_version:
            return False, "Version conflict"
        
        current.verification_state = new_verification_state
        current.verification_confidence = verification_confidence
        current.last_verification_at = datetime.utcnow()
        current.version += 1
        
        if self._save_lifecycle(current):
            self._record_history(LifecycleEvent(
                event_id=f"evt_{uuid.uuid4().hex[:16]}",
                finding_id=finding_id,
                event_type="verification_updated",
                previous_verification_state=current.verification_state.value,
                new_verification_state=new_verification_state.value,
                actor_id=actor_id,
                actor_name=actor_name,
                reason=reason,
                metadata={"verification_confidence": verification_confidence},
            ))
            return True, "Reverification requested"
        return False, "Failed to update verification state"
    
    def get_lifecycle(self, finding_id: int) -> Optional[FindingLifecycle]:
        """Get the current lifecycle state of a finding."""
        return self._get_lifecycle(finding_id)
    
    def get_history(self, finding_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get lifecycle history for a finding."""
        rows = execute_query(
            """SELECT * FROM security_finding_history 
               WHERE finding_id = ? ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
            (finding_id, limit, offset), fetch=True
        )
        return [dict(row) for row in rows] if rows else []
    
    def get_finding_with_lifecycle(self, finding_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Get finding with its lifecycle state."""
        rows = execute_query(
            """SELECT f.*, l.lifecycle_state, l.verification_state, l.resolution_type,
                      l.resolution_reason, l.resolved_at, l.resolved_by,
                      l.acknowledged_at, l.acknowledged_by, l.remediation_started_at,
                      l.remediation_started_by, l.resolved_at, l.resolved_by,
                      l.accepted_risk_at, l.accepted_risk_by, l.risk_acceptance_reason,
                      l.reopened_count, l.verification_state, l.verification_confidence,
                      l.last_verification_at, l.version
               FROM security_findings f
               LEFT JOIN security_finding_lifecycle l ON f.id = l.finding_id
               WHERE f.id = ? AND f.run_id IN (
                   SELECT id FROM autonomous_runs WHERE user_id = ? AND run_type = 'security'
               )""",
            (finding_id, user_id), fetch=True
        )
        if not rows:
            return None
        
        finding = dict(rows[0])
        # Add lifecycle fields
        finding["lifecycle_state"] = finding.get("lifecycle_state", "open")
        finding["verification_state"] = finding.get("verification_state", "candidate")
        finding["verification_confidence"] = finding.get("verification_confidence", 0.5)
        finding["resolution_type"] = finding.get("resolution_type")
        finding["resolution_reason"] = finding.get("resolution_reason")
        finding["resolved_at"] = finding.get("resolved_at")
        finding["resolved_by"] = finding.get("resolved_by")
        finding["acknowledged_at"] = finding.get("acknowledged_at")
        finding["acknowledged_by"] = finding.get("acknowledged_by")
        finding["remediation_started_at"] = finding.get("remediation_started_at")
        finding["remediation_started_by"] = finding.get("remediation_started_by")
        finding["resolved_by"] = finding.get("resolved_by")
        finding["accepted_risk_at"] = finding.get("accepted_risk_at")
        finding["accepted_risk_by"] = finding.get("accepted_risk_by")
        finding["risk_acceptance_reason"] = finding.get("risk_acceptance_reason")
        finding["reopened_count"] = finding.get("reopened_count", 0)
        finding["verification_confidence"] = finding.get("verification_confidence", 0.5)
        finding["version"] = finding.get("version", 1)
        return finding


# Global lifecycle manager instance
_lifecycle_manager = FindingLifecycleManager()


def get_lifecycle_manager() -> FindingLifecycleManager:
    """Get the global lifecycle manager instance."""
    return _lifecycle_manager