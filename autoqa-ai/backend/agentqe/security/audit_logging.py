"""
Audit Logging – structured audit logging for security assessments.

This module provides structured, tamper-evident audit logging for all
security-relevant events in the active testing lifecycle.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from database.db import execute_query
from agentqe.security.security_config import CONFIG

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""
    # Assessment lifecycle
    ASSESSMENT_CREATED = "assessment_created"
    ASSESSMENT_STARTED = "assessment_started"
    ASSESSMENT_COMPLETED = "assessment_completed"
    ASSESSMENT_FAILED = "assessment_failed"
    ASSESSMENT_CANCELLED = "assessment_cancelled"
    ASSESSMENT_BLOCKED = "assessment_blocked"
    
    # Authorization
    AUTHORIZATION_CREATED = "authorization_created"
    AUTHORIZATION_VERIFIED = "authorization_verified"
    AUTHORIZATION_REVOKED = "authorization_revoked"
    AUTHORIZATION_EXPIRED = "authorization_expired"
    AUTHORIZATION_FAILED = "authorization_failed"
    
    # Policy
    POLICY_EVALUATED = "policy_evaluated"
    POLICY_ALLOWED = "policy_allowed"
    POLICY_DENIED = "policy_denied"
    POLICY_DRY_RUN = "policy_dry_run"
    
    # Confirmation
    CONFIRMATION_REQUESTED = "confirmation_requested"
    CONFIRMATION_GIVEN = "confirmation_given"
    CONFIRMATION_EXPIRED = "confirmation_expired"
    CONFIRMATION_INVALID = "confirmation_invalid"
    
    # Execution
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_CANCELLED = "execution_cancelled"
    EXECUTION_BUDGET_EXCEEDED = "execution_budget_exceeded"
    
    # Network safety
    NETWORK_BLOCKED = "network_blocked"
    NETWORK_REDIRECT_BLOCKED = "network_redirect_blocked"
    DNS_REBINDING_ATTEMPT = "dns_rebinding_attempt"
    
    # Dry run
    DRY_RUN_REQUESTED = "dry_run_requested"
    DRY_RUN_COMPLETED = "dry_run_completed"
    
    # Reporting
    REPORT_GENERATED = "report_generated"
    REPORT_FAILED = "report_failed"


@dataclass(frozen=True)
class AuditEvent:
    """Immutable audit event record."""
    event_type: AuditEventType
    timestamp: datetime
    user_id: int
    run_id: Optional[int] = None
    target_url: Optional[str] = None
    normalized_target: Optional[str] = None
    profile: Optional[str] = None
    mode: Optional[str] = None  # 'passive' or 'active'
    decision: Optional[str] = None
    reason: Optional[str] = None
    reason_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: f"audit_{int(time.time()*1000)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'user_id': self.user_id,
            'run_id': self.run_id,
            'target_url': self.target_url,
            'normalized_target': self.normalized_target,
            'profile': self.profile,
            'mode': self.mode,
            'decision': self.decision,
            'reason': self.reason,
            'reason_code': self.reason_code,
            'metadata': self.metadata,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class AuditLogger:
    """
    Thread-safe audit logger with database persistence.
    
    Provides structured, tamper-evident audit logging for security events.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._buffer: List[AuditEvent] = []
        self._buffer_size = 100
        self._flush_interval = 5.0  # seconds
        self._last_flush = time.time()
        self._db_enabled = True
        self._init_db()
    
    def _init_db(self):
        """Initialize audit log table."""
        try:
            execute_query("""
                CREATE TABLE IF NOT EXISTS security_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    user_id INTEGER NOT NULL,
                    run_id INTEGER,
                    target_url TEXT,
                    normalized_target TEXT,
                    profile TEXT,
                    mode TEXT,
                    decision TEXT,
                    reason TEXT,
                    reason_code TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Create index for common queries
            execute_query("CREATE INDEX IF NOT EXISTS idx_audit_user_id ON security_audit_log(user_id)")
            execute_query("CREATE INDEX IF NOT EXISTS idx_audit_run_id ON security_audit_log(run_id)")
            execute_query("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON security_audit_log(timestamp)")
            execute_query("CREATE INDEX IF NOT EXISTS idx_audit_event_type ON security_audit_log(event_type)")
        except Exception as e:
            logger.warning(f"Failed to initialize audit log table: {e}")
            self._db_enabled = False
    
    def log(self, event: AuditEvent) -> None:
        """Log an audit event."""
        # Add to buffer
        with self._lock:
            self._buffer.append(event)
            # Check if we should flush
            if len(self._buffer) >= self._buffer_size or \
               time.time() - self._last_flush > self._flush_interval:
                self._flush()
    
    def _flush(self) -> None:
        """Flush buffer to database."""
        if not self._buffer or not self._db_enabled:
            return
        
        events_to_write = self._buffer[:]
        self._buffer.clear()
        self._last_flush = time.time()
        
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            for event in events_to_write:
                cursor.execute(
                    """INSERT INTO security_audit_log
                       (event_id, event_type, timestamp, user_id, run_id,
                        target_url, normalized_target, profile, mode,
                        decision, reason, reason_code, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.event_id,
                        event.event_type.value,
                        event.timestamp.isoformat(),
                        event.user_id,
                        event.run_id,
                        event.target_url,
                        event.normalized_target,
                        event.profile,
                        event.mode,
                        event.decision,
                        event.reason,
                        event.reason_code,
                        json.dumps(event.metadata, default=str),
                    )
                )
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to flush audit log: {e}")
            # Re-add to buffer on failure
            with self._lock:
                self._buffer = events_to_write + self._buffer
    
    def force_flush(self) -> None:
        """Force flush of audit buffer."""
        with self._lock:
            self._flush()
    
    def query_events(self, 
                     user_id: Optional[int] = None,
                     run_id: Optional[int] = None,
                     event_type: Optional[AuditEventType] = None,
                     start_time: Optional[datetime] = None,
                     end_time: Optional[datetime] = None,
                     limit: int = 100,
                     offset: int = 0) -> List[Dict[str, Any]]:
        """Query audit events with filters."""
        if not self._db_enabled:
            return []
        
        try:
            conditions = []
            params = []
            
            if user_id is not None:
                conditions.append("user_id = ?")
                params.append(user_id)
            if run_id is not None:
                conditions.append("run_id = ?")
                params.append(run_id)
            if event_type is not None:
                conditions.append("event_type = ?")
                params.append(event_type.value)
            if start_time is not None:
                conditions.append("timestamp >= ?")
                params.append(start_time.isoformat())
            if end_time is not None:
                conditions.append("timestamp <= ?")
                params.append(end_time.isoformat())
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            query = f"""
                SELECT * FROM security_audit_log
                {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            
            rows = execute_query(query, tuple(params), fetch=True)
            return [dict(row) for row in rows] if rows else []
        except Exception as e:
            logger.error(f"Failed to query audit events: {e}")
            return []


# Global audit logger instance
_audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger."""
    return _audit_logger


def log_event(event_type: AuditEventType,
              user_id: int,
              run_id: Optional[int] = None,
              target_url: Optional[str] = None,
              normalized_target: Optional[str] = None,
              profile: Optional[str] = None,
              mode: Optional[str] = None,
              decision: Optional[str] = None,
              reason: Optional[str] = None,
              reason_code: Optional[str] = None,
              metadata: Optional[Dict[str, Any]] = None) -> AuditEvent:
    """Log an audit event."""
    event = AuditEvent(
        event_type=event_type,
        timestamp=datetime.utcnow(),
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        normalized_target=normalized_target,
        profile=profile,
        mode=mode,
        decision=decision,
        reason=reason,
        reason_code=reason_code,
        metadata=metadata or {},
    )
    get_audit_logger().log(event)
    return event


# Convenience functions for common audit events
def log_assessment_created(user_id: int, run_id: int, target_url: str, 
                           mode: str, profile: str) -> AuditEvent:
    return log_event(
        AuditEventType.ASSESSMENT_CREATED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        mode=mode,
        profile=profile,
        decision="created",
        reason="Security assessment created",
    )


def log_assessment_started(user_id: int, run_id: int, target_url: str) -> AuditEvent:
    return log_event(
        AuditEventType.ASSESSMENT_STARTED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        decision="started",
        reason="Assessment execution started",
    )


def log_assessment_completed(user_id: int, run_id: int, target_url: str,
                             findings_count: int) -> AuditEvent:
    return log_event(
        AuditEventType.ASSESSMENT_COMPLETED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        decision="completed",
        reason="Assessment completed successfully",
        metadata={'findings_count': findings_count},
    )


def log_assessment_failed(user_id: int, run_id: int, target_url: str,
                          error: str) -> AuditEvent:
    return log_event(
        AuditEventType.ASSESSMENT_FAILED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        decision="failed",
        reason=f"Assessment failed: {error}",
        reason_code="ASSESSMENT_FAILED",
    )


def log_assessment_cancelled(user_id: int, run_id: int, target_url: str) -> AuditEvent:
    return log_event(
        AuditEventType.ASSESSMENT_CANCELLED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        decision="cancelled",
        reason="Assessment cancelled by user",
    )


def log_policy_evaluated(user_id: int, run_id: int, target_url: str,
                         profile: str, mode: str, decision: str,
                         reason: str, reason_code: str) -> AuditEvent:
    return log_event(
        AuditEventType.POLICY_EVALUATED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        profile=profile,
        mode=mode,
        decision=decision,
        reason=reason,
        reason_code=reason_code,
    )


def log_policy_allowed(user_id: int, run_id: int, target_url: str,
                       profile: str, mode: str) -> AuditEvent:
    return log_event(
        AuditEventType.POLICY_ALLOWED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        profile=profile,
        mode=mode,
        decision="allowed",
        reason="Active assessment allowed by policy",
    )


def log_policy_denied(user_id: int, run_id: int, target_url: str,
                      profile: str, mode: str, reason: str,
                      reason_code: str) -> AuditEvent:
    return log_event(
        AuditEventType.POLICY_DENIED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        profile=profile,
        mode=mode,
        decision="denied",
        reason=reason,
        reason_code=reason_code,
    )


def log_confirmation_requested(user_id: int, run_id: int, target_url: str) -> AuditEvent:
    return log_event(
        AuditEventType.CONFIRMATION_REQUESTED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        decision="confirmation_required",
        reason="Active assessment requires explicit user confirmation",
    )


def log_confirmation_given(user_id: int, run_id: int, target_url: str,
                           confirmation_token: str) -> AuditEvent:
    return log_event(
        AuditEventType.CONFIRMATION_GIVEN,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        decision="confirmed",
        reason="User confirmed active assessment",
        metadata={'confirmation_token': confirmation_token[:8] + '...'},
    )


def log_execution_budget_exceeded(user_id: int, run_id: int, target_url: str,
                                  budget_type: str, limit: Any, used: Any) -> AuditEvent:
    return log_event(
        AuditEventType.EXECUTION_BUDGET_EXCEEDED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        decision="budget_exceeded",
        reason=f"Budget exceeded: {budget_type} (limit: {limit}, used: {used})",
        reason_code="BUDGET_EXCEEDED",
        metadata={'budget_type': budget_type, 'limit': str(limit), 'used': str(used)},
    )


def log_network_blocked(user_id: int, run_id: int, target_url: str,
                        blocked_url: str, reason: str, reason_code: str) -> AuditEvent:
    return log_event(
        AuditEventType.NETWORK_BLOCKED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        decision="blocked",
        reason=f"Network request blocked: {reason}",
        reason_code=reason_code,
        metadata={'blocked_url': blocked_url},
    )


def log_dry_run_requested(user_id: int, run_id: int, target_url: str,
                          profile: str, plan: Dict[str, Any]) -> AuditEvent:
    return log_event(
        AuditEventType.DRY_RUN_REQUESTED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        profile=profile,
        mode='active',
        decision="dry_run",
        reason="Dry-run plan generated for active assessment",
        metadata={'plan': plan},
    )


def log_report_generated(user_id: int, run_id: int, target_url: str) -> AuditEvent:
    return log_event(
        AuditEventType.REPORT_GENERATED,
        user_id=user_id,
        run_id=run_id,
        target_url=target_url,
        decision="generated",
        reason="Security assessment report generated",
    )