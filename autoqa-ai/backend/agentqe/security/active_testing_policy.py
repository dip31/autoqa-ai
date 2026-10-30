"""
Active Testing Policy – centralized policy engine for active security testing.

This module determines whether an active security assessment is allowed to proceed,
based on user identity, target authorization, scope, network safety, resource budgets,
and explicit user confirmation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from agentqe.security.security_config import CONFIG
from agentqe.security.authorization.authorization_repository import get_verified_authorization
from agentqe.security.scope_validator import validate_url_scope, ScopeDefinition
from agentqe.security.network_safety import resolve_hostname, classify_ip_address

logger = logging.getLogger(__name__)


class PolicyDecision(Enum):
    """Possible outcomes of policy evaluation."""
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_AUTHORIZATION = "requires_authorization"
    OUT_OF_SCOPE = "out_of_scope"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNSAFE_TARGET = "unsafe_target"
    UNSUPPORTED = "unsupported"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    DRY_RUN_ONLY = "dry_run_only"


@dataclass(frozen=True)
class PolicyDecisionResult:
    """Result of a policy evaluation."""
    decision: PolicyDecision
    reason: str
    reason_code: str
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, 'metadata', {})


@dataclass(frozen=True)
class ActiveTestingContext:
    """Context for active testing policy evaluation."""
    user_id: int
    target_url: str
    normalized_target: str
    scope: ScopeDefinition
    mode: str  # 'passive' or 'active'
    profile: str  # 'passive_only', 'safe_active', 'custom'
    dry_run: bool = False
    confirmed: bool = False
    confirmation_token: Optional[str] = None
    profile_limits: Optional[Dict[str, Any]] = None


class ActiveTestingPolicy:
    """
    Centralized policy engine for active security testing.
    
    Evaluates whether an active security assessment is allowed to proceed.
    """

    def __init__(self, config: Optional[Any] = None):
        self.config = config or CONFIG

    def evaluate(self, context: ActiveTestingContext) -> PolicyDecisionResult:
        """
        Evaluate whether an active assessment can proceed.
        
        Returns a PolicyDecisionResult with the decision and reasoning.
        """
        # 1. If passive mode, always allow (handled by existing passive flow)
        if context.mode == 'passive':
            return PolicyDecisionResult(
                decision=PolicyDecision.ALLOWED,
                reason="Passive assessment mode allowed",
                reason_code="PASSIVE_MODE"
            )

        # 2. Validate active mode requirements
        if context.mode != 'active':
            return PolicyDecisionResult(
                decision=PolicyDecision.DENIED,
                reason=f"Invalid assessment mode: {context.mode}",
                reason_code="INVALID_MODE"
            )

        # 3. Check target authorization for active testing
        auth_result = self._check_active_authorization(context)
        if auth_result.decision != PolicyDecision.ALLOWED:
            return auth_result

        # 4. Validate scope
        scope_result = self._check_scope(context)
        if scope_result.decision != PolicyDecision.ALLOWED:
            return scope_result

        # 5. Network safety validation
        network_result = self._check_network_safety(context)
        if network_result.decision != PolicyDecision.ALLOWED:
            return network_result

        # 5. Check resource budgets
        budget_result = self._check_budgets(context)
        if budget_result.decision != PolicyDecision.ALLOWED:
            return budget_result

        # 6. Check confirmation requirement
        if not context.dry_run and not context.confirmed:
            return PolicyDecisionResult(
                decision=PolicyDecision.REQUIRES_CONFIRMATION,
                reason="Active assessment requires explicit user confirmation",
                reason_code="REQUIRES_CONFIRMATION",
                metadata={"requires_confirmation": True}
            )

        # 7. Validate confirmation token if provided
        if context.confirmed and not self._validate_confirmation(context):
            return PolicyDecisionResult(
                decision=PolicyDecision.DENIED,
                reason="Invalid or expired confirmation token",
                reason_code="INVALID_CONFIRMATION"
            )

        # 8. Check profile support
        profile_result = self._check_profile(context)
        if profile_result.decision != PolicyDecision.ALLOWED:
            return profile_result

        # All checks passed
        return PolicyDecisionResult(
            decision=PolicyDecision.ALLOWED,
            reason="Active assessment allowed",
            reason_code="ALLOWED",
            metadata={
                "profile": context.profile,
                "dry_run": context.dry_run,
                "confirmed": context.confirmed,
            }
        )

    def _check_active_authorization(self, context: ActiveTestingContext) -> PolicyDecisionResult:
        """Check if user has active testing authorization for the target."""
        # Check if target has verified authorization
        auth = get_verified_authorization(context.user_id, context.scope.host)
        if not auth:
            return PolicyDecisionResult(
                decision=PolicyDecision.REQUIRES_AUTHORIZATION,
                reason="Target not authorized for security testing",
                reason_code="TARGET_NOT_AUTHORIZED",
                metadata={"hostname": context.scope.host}
            )

        # Check if authorization explicitly permits active testing
        # For now, we require a separate active_testing flag or extended scope
        # In the current schema, we'll check if the authorization allows active testing
        # by checking if the scope includes active testing permissions
        # For Phase 5A, we'll add a simple check: authorization must be verified
        # and we'll add an active_testing_allowed field in a future migration
        # For now, we'll allow active testing if the authorization is verified
        # and the user has explicitly requested active mode
        
        # Check if authorization has expired
        if auth.expires_at and auth.expires_at < datetime.utcnow():
            return PolicyDecisionResult(
                decision=PolicyDecision.DENIED,
                reason="Authorization has expired",
                reason_code="AUTHORIZATION_EXPIRED"
            )

        # Check if authorization has been revoked
        if auth.revoked_at:
            return PolicyDecisionResult(
                decision=PolicyDecision.DENIED,
                reason="Authorization has been revoked",
                reason_code="AUTHORIZATION_REVOKED"
            )

        return PolicyDecisionResult(
            decision=PolicyDecision.ALLOWED,
            reason="Target authorized for active testing",
            reason_code="AUTHORIZED"
        )

    def _check_scope(self, context: ActiveTestingContext) -> PolicyDecisionResult:
        """Validate that the target is within the authorized scope."""
        result = validate_url_scope(context.normalized_target, context.scope)
        if not result.allowed:
            return PolicyDecisionResult(
                decision=PolicyDecision.OUT_OF_SCOPE,
                reason=result.message,
                reason_code=result.reason_code,
                metadata={"normalized_url": result.normalized_url}
            )
        return PolicyDecisionResult(
            decision=PolicyDecision.ALLOWED,
            reason="Target within authorized scope",
            reason_code="SCOPE_OK"
        )

    def _check_network_safety(self, context: ActiveTestingContext) -> PolicyDecisionResult:
        """Validate network safety - DNS resolution and IP address checks."""
        # Resolve hostname
        dns_result = resolve_hostname(context.scope.host)
        if not dns_result.allowed:
            return PolicyDecisionResult(
                decision=PolicyDecision.UNSAFE_TARGET,
                reason=f"Target resolves to prohibited IP address: {dns_result.reason_code}",
                reason_code=dns_result.reason_code,
                metadata={"hostname": context.scope.host, "ips": [str(ip) for ip in dns_result.ips]}
            )

        # Check each resolved IP
        for ip in dns_result.ips:
            allowed, reason = classify_ip_address(str(ip))
            if not allowed:
                return PolicyDecisionResult(
                    decision=PolicyDecision.UNSAFE_TARGET,
                    reason=f"Target IP {ip} is prohibited: {reason}",
                    reason_code=reason,
                    metadata={"ip": str(ip)}
                )

        return PolicyDecisionResult(
            decision=PolicyDecision.ALLOWED,
            reason="Network safety checks passed",
            reason_code="NETWORK_SAFETY_OK"
        )

    def _check_budgets(self, context: ActiveTestingContext) -> PolicyDecisionResult:
        """Validate resource budgets against configured limits."""
        limits = self._get_effective_limits(context)
        
        # Check duration limit
        if limits.get('max_duration_seconds', 0) > self.config.max_duration_seconds:
            return PolicyDecisionResult(
                decision=PolicyDecision.BUDGET_EXCEEDED,
                reason=f"Requested duration exceeds maximum allowed ({self.config.max_duration_seconds}s)",
                reason_code="DURATION_EXCEEDED"
            )

        # Check request rate limit
        if limits.get('max_requests_per_second', 0) > self.config.max_requests_per_second:
            return PolicyDecisionResult(
                decision=PolicyDecision.BUDGET_EXCEEDED,
                reason=f"Requested rate exceeds maximum allowed ({self.config.max_requests_per_second} req/s)",
                reason_code="RATE_EXCEEDED"
            )

        # Check concurrent runs limit
        # This would need a DB check in practice
        # For now, we'll rely on the runtime enforcement in security_runner.py

        return PolicyDecisionResult(
            decision=PolicyDecision.ALLOWED,
            reason="Budget checks passed",
            reason_code="BUDGETS_OK"
        )

    def _get_effective_limits(self, context: ActiveTestingContext) -> Dict[str, Any]:
        """Get effective limits from profile and config."""
        base_limits = {
            'max_duration_seconds': self.config.max_duration_seconds,
            'max_requests_per_second': self.config.max_requests_per_second,
            'max_response_size_bytes': self.config.max_response_size_bytes,
            'max_redirects': self.config.max_redirects,
            'max_pages': self.config.max_pages,
            'max_depth': self.config.max_depth,
        }

        # Apply profile-specific limits
        if context.profile_limits:
            base_limits.update(context.profile_limits)

        return base_limits

    def _check_profile(self, context: ActiveTestingContext) -> PolicyDecisionResult:
        """Validate that the requested profile is supported."""
        supported_profiles = ['passive_only', 'safe_active', 'custom']
        if context.profile not in supported_profiles:
            return PolicyDecisionResult(
                decision=PolicyDecision.UNSUPPORTED,
                reason=f"Unsupported testing profile: {context.profile}",
                reason_code="UNSUPPORTED_PROFILE"
            )

        # For Phase 5A, only passive_only and safe_active are supported
        if context.profile == 'custom':
            return PolicyDecisionResult(
                decision=PolicyDecision.UNSUPPORTED,
                reason="Custom profiles not yet supported in Phase 5A",
                reason_code="CUSTOM_PROFILE_UNSUPPORTED"
            )

        return PolicyDecisionResult(
            decision=PolicyDecision.ALLOWED,
            reason=f"Profile '{context.profile}' supported",
            reason_code="PROFILE_OK"
        )

    def _validate_confirmation(self, context: ActiveTestingContext) -> bool:
        """Validate the confirmation token."""
        # In a real implementation, this would validate a short-lived token
        # For Phase 5A, we'll do a simple check
        if not context.confirmation_token:
            return False
        # In a real implementation, validate token signature, expiration, and binding to context
        # For Phase 5A, we'll just check it's not empty
        return len(context.confirmation_token) > 0

    def get_dry_run_plan(self, context: ActiveTestingContext) -> Dict[str, Any]:
        """
        Generate a dry-run execution plan without executing active checks.
        
        Returns a plan showing what would be executed, what would be blocked, and why.
        """
        # Create a copy of context for dry-run evaluation
        dry_run_context = ActiveTestingContext(
            user_id=context.user_id,
            target_url=context.target_url,
            normalized_target=context.normalized_target,
            scope=context.scope,
            mode='active',
            profile=context.profile,
            dry_run=True,
            confirmed=False,
        )

        # Evaluate policy without executing
        policy_result = self.evaluate(dry_run_context)

        # Determine which validators would run
        from agentqe.security.validators import _validator_modules as _validator_names
        from agentqe.security.validators import _validator_class_names
        
        eligible_validators = []
        blocked_validators = []

        for name in _validator_names:
            cls_name = _validator_class_names.get(name)
            if cls_name:
                eligible_validators.append({
                    'name': name,
                    'class': cls_name,
                    'status': 'planned'
                })
            else:
                blocked_validators.append({
                    'name': name,
                    'reason': 'No class mapping found',
                    'status': 'blocked'
                })

        return {
            'policy_decision': policy_result.decision.value,
            'reason': policy_result.reason,
            'reason_code': policy_result.reason_code,
            'eligible_validators': eligible_validators,
            'blocked_validators': blocked_validators,
            'effective_limits': self._get_effective_limits(context),
            'scope': {
                'scheme': context.scope.scheme,
                'host': context.scope.host,
                'port': context.scope.port,
                'path_prefix': context.scope.path_prefix,
                'allow_subdomains': context.scope.allow_subdomains,
            },
            'profile': context.profile,
            'dry_run': True,
            'requires_confirmation': not context.dry_run and policy_result.decision == PolicyDecision.ALLOWED,
        }


# Convenience function for easy access
def evaluate_active_policy(context: ActiveTestingContext) -> PolicyDecisionResult:
    """Convenience function to evaluate active testing policy."""
    policy = ActiveTestingPolicy()
    return policy.evaluate(context)


def generate_dry_run_plan(context: ActiveTestingContext) -> Dict[str, Any]:
    """Convenience function to generate a dry-run plan."""
    policy = ActiveTestingPolicy()
    return policy.get_dry_run_plan(context)