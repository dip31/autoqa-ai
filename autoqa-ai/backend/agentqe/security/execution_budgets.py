"""
Execution Budgets – centralized resource budget management for active security testing.

This module provides centralized budget tracking and enforcement for active
security assessments. It ensures that assessments stay within their allocated
resource budgets and can be safely terminated when limits are exceeded.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Any, List
from typing import TYPE_CHECKING

from agentqe.security.security_config import CONFIG

if TYPE_CHECKING:
    from agentqe.security.active_testing_profiles import ProfileRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BudgetLimits:
    """Immutable budget limits for an assessment."""
    max_duration_seconds: int
    max_requests_per_second: float
    max_total_requests: int
    max_response_size_bytes: int
    max_redirects: int
    max_pages: int
    max_depth: int
    max_concurrent_runs: int
    max_response_time_seconds: float = 30.0


@dataclass
class BudgetUsage:
    """Current budget usage for an assessment."""
    run_id: int
    started_at: datetime
    requests_made: int = 0
    total_bytes_received: int = 0
    redirects_followed: int = 0
    pages_crawled: int = 0
    max_depth_reached: int = 0
    last_request_time: float = 0.0
    request_times: List[float] = field(default_factory=list)
    budget_exceeded: bool = False
    exceeded_reason: Optional[str] = None


@dataclass
class BudgetConfig:
    """Budget configuration for an assessment."""
    limits: BudgetLimits
    profile_id: str
    run_id: int
    user_id: int


class BudgetManager:
    """
    Manages execution budgets for active security assessments.
    
    Provides thread-safe budget tracking and enforcement.
    """
    
    def __init__(self):
        self._budgets: Dict[int, BudgetUsage] = {}
        self._lock = threading.RLock()
        self._active_runs: Dict[int, BudgetConfig] = {}
    
    def start_budget(self, config: BudgetConfig) -> BudgetUsage:
        """Start tracking budget for a new assessment."""
        limits = self._get_profile_limits(config.profile_id)
        
        budget_limits = BudgetLimits(
            max_duration_seconds=min(limits.get('max_duration_seconds', CONFIG.max_duration_seconds),
                                    CONFIG.max_duration_seconds),
            max_requests_per_second=min(limits.get('max_requests_per_second', CONFIG.max_requests_per_second),
                                       CONFIG.max_requests_per_second),
            max_total_requests=limits.get('max_total_requests', 1000),
            max_response_size_bytes=min(limits.get('max_response_size_bytes', CONFIG.max_response_size_bytes),
                                       CONFIG.max_response_size_bytes),
            max_redirects=min(limits.get('max_redirects', CONFIG.max_redirects),
                             CONFIG.max_redirects),
            max_pages=min(limits.get('max_pages', CONFIG.max_pages),
                         CONFIG.max_pages),
            max_depth=min(limits.get('max_depth', CONFIG.max_depth),
                         CONFIG.max_depth),
            max_concurrent_runs=min(limits.get('max_concurrent_runs', CONFIG.max_concurrent_runs),
                                   CONFIG.max_concurrent_runs),
        )
        
        usage = BudgetUsage(
            run_id=config.run_id,
            started_at=datetime.utcnow(),
        )
        
        with self._lock:
            self._budgets[config.run_id] = usage
            self._active_runs[config.run_id] = BudgetConfig(
                limits=budget_limits,
                profile_id=config.profile_id,
                run_id=config.run_id,
                user_id=config.user_id,
            )
        
        logger.info(f"Started budget tracking for run {config.run_id} with profile {config.profile_id}")
        return usage
    
    def _get_profile_limits(self, profile_id: str) -> Dict[str, Any]:
        """Get limits from profile registry."""
        from agentqe.security.active_testing_profiles import get_profile_limits
        return get_profile_limits(profile_id)
    
    def record_request(self, run_id: int, response_size: int = 0, 
                       is_redirect: bool = False, page_crawled: bool = False,
                       depth: int = 0) -> bool:
        """
        Record a request and check if budget is exceeded.
        
        Returns True if request is allowed, False if budget exceeded.
        """
        with self._lock:
            usage = self._budgets.get(run_id)
            config = self._active_runs.get(run_id)
            
            if not usage or not config:
                logger.warning(f"No budget found for run {run_id}")
                return False
            
            if usage.budget_exceeded:
                return False
            
            now = time.time()
            usage.requests_made += 1
            usage.total_bytes_received += response_size
            usage.last_request_time = now
            usage.request_times.append(now)
            
            if is_redirect:
                usage.redirects_followed += 1
            
            if page_crawled:
                usage.pages_crawled += 1
                usage.max_depth_reached = max(usage.max_depth_reached, depth)
            
            # Check budgets
            exceeded, reason = self._check_budgets(usage, config.limits)
            if exceeded:
                usage.budget_exceeded = True
                usage.exceeded_reason = reason
                logger.warning(f"Budget exceeded for run {run_id}: {reason}")
                return False
            
            return True
    
    def _check_budgets(self, usage: BudgetUsage, limits: BudgetLimits) -> tuple:
        """Check if any budget limits have been exceeded."""
        # Duration check
        elapsed = time.time() - usage.started_at.timestamp()
        if elapsed > limits.max_duration_seconds:
            return True, f"Duration exceeded ({elapsed:.1f}s > {limits.max_duration_seconds}s)"
        
        # Request rate check (sliding window of 1 second)
        now = time.time()
        recent_requests = [t for t in usage.request_times if now - t < 1.0]
        if len(recent_requests) > limits.max_requests_per_second:
            return True, f"Request rate exceeded ({len(recent_requests)}/s > {limits.max_requests_per_second}/s)"
        
        # Total requests check
        if usage.requests_made > limits.max_total_requests:
            return True, f"Total requests exceeded ({usage.requests_made} > {limits.max_total_requests})"
        
        # Response size check
        if usage.total_bytes_received > limits.max_response_size_bytes:
            return True, f"Total response size exceeded ({usage.total_bytes_received} > {limits.max_response_size_bytes})"
        
        # Redirects check
        if usage.redirects_followed > limits.max_redirects:
            return True, f"Redirects exceeded ({usage.redirects_followed} > {limits.max_redirects})"
        
        # Pages check
        if usage.pages_crawled > limits.max_pages:
            return True, f"Pages crawled exceeded ({usage.pages_crawled} > {limits.max_pages})"
        
        # Depth check
        if usage.max_depth_reached > limits.max_depth:
            return True, f"Crawl depth exceeded ({usage.max_depth_reached} > {limits.max_depth})"
        
        return False, None
    
    def get_usage(self, run_id: int) -> Optional[BudgetUsage]:
        """Get current budget usage for a run."""
        with self._lock:
            return self._budgets.get(run_id)
    
    def get_remaining_budget(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Get remaining budget for a run."""
        with self._lock:
            usage = self._budgets.get(run_id)
            config = self._active_runs.get(run_id)
            
            if not usage or not config:
                return None
            
            elapsed = time.time() - usage.started_at.timestamp()
            
            return {
                'duration': {
                    'used': elapsed,
                    'limit': config.limits.max_duration_seconds,
                    'remaining': max(0, config.limits.max_duration_seconds - elapsed),
                },
                'requests': {
                    'used': usage.requests_made,
                    'limit': config.limits.max_total_requests,
                    'remaining': max(0, config.limits.max_total_requests - usage.requests_made),
                },
                'requests_per_second': {
                    'used': len([t for t in usage.request_times if time.time() - t < 1.0]),
                    'limit': config.limits.max_requests_per_second,
                },
                'response_size': {
                    'used': usage.total_bytes_received,
                    'limit': config.limits.max_response_size_bytes,
                    'remaining': max(0, config.limits.max_response_size_bytes - usage.total_bytes_received),
                },
                'redirects': {
                    'used': usage.redirects_followed,
                    'limit': config.limits.max_redirects,
                    'remaining': max(0, config.limits.max_redirects - usage.redirects_followed),
                },
                'pages': {
                    'used': usage.pages_crawled,
                    'limit': config.limits.max_pages,
                    'remaining': max(0, config.limits.max_pages - usage.pages_crawled),
                },
                'depth': {
                    'used': usage.max_depth_reached,
                    'limit': config.limits.max_depth,
                },
                'exceeded': usage.budget_exceeded,
                'exceeded_reason': usage.exceeded_reason,
            }
    
    def check_duration(self, run_id: int) -> bool:
        """Check if duration limit has been exceeded."""
        with self._lock:
            usage = self._budgets.get(run_id)
            config = self._active_runs.get(run_id)
            
            if not usage or not config:
                return False
            
            elapsed = time.time() - usage.started_at.timestamp()
            return elapsed <= config.limits.max_duration_seconds
    
    def is_exceeded(self, run_id: int) -> bool:
        """Check if budget has been exceeded."""
        with self._lock:
            usage = self._budgets.get(run_id)
            return usage.budget_exceeded if usage else True
    
    def get_exceeded_reason(self, run_id: int) -> Optional[str]:
        """Get the reason budget was exceeded."""
        with self._lock:
            usage = self._budgets.get(run_id)
            return usage.exceeded_reason if usage else "Budget not found"
    
    def finish_budget(self, run_id: int) -> Optional[BudgetUsage]:
        """Finish budget tracking and return final usage."""
        with self._lock:
            usage = self._budgets.pop(run_id, None)
            self._active_runs.pop(run_id, None)
            if usage:
                logger.info(f"Finished budget tracking for run {run_id}: "
                           f"{usage.requests_made} requests, "
                           f"{usage.total_bytes_received} bytes, "
                           f"{usage.pages_crawled} pages")
            return usage
    
    def cleanup_stale_budgets(self, max_age_seconds: int = 3600) -> int:
        """Clean up stale budget entries."""
        with self._lock:
            now = time.time()
            stale_ids = [
                run_id for run_id, usage in self._budgets.items()
                if now - usage.started_at.timestamp() > max_age_seconds
            ]
            for run_id in stale_ids:
                self._budgets.pop(run_id, None)
                self._active_runs.pop(run_id, None)
            if stale_ids:
                logger.info(f"Cleaned up {len(stale_ids)} stale budget entries")
            return len(stale_ids)


# Global budget manager instance
_budget_manager = BudgetManager()


def get_budget_manager() -> BudgetManager:
    """Get the global budget manager."""
    return _budget_manager


def start_budget(run_id: int, profile_id: str, user_id: int) -> Any:
    """Start budget tracking for a run."""
    from agentqe.security.execution_budgets import BudgetManager, BudgetConfig
    manager = get_budget_manager()
    config = BudgetConfig(
        limits=None,  # Will be populated from profile
        profile_id=profile_id,
        run_id=run_id,
        user_id=user_id,
    )
    return manager.start_budget(config)


def record_request(run_id: int, response_size: int = 0,
                   is_redirect: bool = False, page_crawled: bool = False,
                   depth: int = 0) -> bool:
    """Record a request against the budget."""
    return get_budget_manager().record_request(run_id, response_size, is_redirect, page_crawled, depth)


def check_budget(run_id: int) -> bool:
    """Check if budget is still valid."""
    return not get_budget_manager().is_exceeded(run_id)


def get_budget_usage(run_id: int) -> Optional[Any]:
    """Get current budget usage."""
    return get_budget_manager().get_usage(run_id)


def get_budget_remaining(run_id: int) -> Optional[Dict[str, Any]]:
    """Get remaining budget."""
    return get_budget_manager().get_remaining_budget(run_id)


def finish_budget(run_id: int) -> Optional[Any]:
    """Finish budget tracking."""
    return get_budget_manager().finish_budget(run_id)


def check_budget_duration(run_id: int) -> bool:
    """Check if duration budget is still valid."""
    return get_budget_manager().check_duration(run_id)