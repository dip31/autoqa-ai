"""
Finding classification utilities – deduplication, severity normalisation, fingerprinting.
"""
from __future__ import annotations

import hashlib
import json
from typing import List
from collections import defaultdict
from urllib.parse import urlparse

from agentqe.interfaces import Finding
from agentqe.security.models import severity_rank


def compute_finding_fingerprint(finding: Finding) -> str:
    """
    Compute a stable fingerprint for a finding to enable deduplication.
    
    Uses stable attributes that identify the underlying security issue:
    - validator_id (source)
    - category
    - normalized affected_url
    - normalized finding_type/classification
    - normalized parameter/field name if available
    
    Does NOT include:
    - run_id (different runs of same issue)
    - timestamp (changes each run)
    - finding_id (unique per creation)
    - specific payload values (can vary)
    """
    # Normalize affected URL - strip query params, fragments, normalize case
    affected_url = ""
    if hasattr(finding, 'metadata') and finding.metadata:
        affected_url = finding.metadata.get("affected_url", "")
    elif hasattr(finding, 'affected_url'):
        affected_url = finding.affected_url
    
    # Normalize URL: lowercase, remove query/fragment, strip trailing slash
    if affected_url:
        parsed = urlparse(affected_url)
        affected_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}".lower()
    
    # Normalize finding type/classification
    finding_type = getattr(finding, 'finding_type', '') or finding.category
    classification = getattr(finding, 'classification', '')
    
    # Extract parameter/field name from evidence or metadata
    param_name = ""
    if hasattr(finding, 'metadata') and finding.metadata:
        param_name = finding.metadata.get('parameter', '') or finding.metadata.get('field_name', '')
        # Also check evidence for parameter name
        if not param_name and hasattr(finding, 'evidence') and finding.evidence:
            if isinstance(finding.evidence, dict):
                param_name = finding.evidence.get('parameter', '') or finding.evidence.get('field_name', '')
    
    # Build fingerprint components
    components = [
        finding.source,                    # validator_id
        finding.category,                  # category
        affected_url,                      # normalized affected URL
        finding_type.lower(),              # finding type
        classification.lower(),            # classification
        param_name.lower(),                # parameter/field name
    ]
    
    # Create stable hash
    fingerprint_str = "|".join(c for c in components if c)
    return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:32]


def classify_findings(findings: List[Finding]) -> List[Finding]:
    """
    Deduplicate findings using stable fingerprints.
    
    Groups findings by stable fingerprint and keeps the one with highest severity.
    Merges evidence from all duplicates.
    """
    from urllib.parse import urlparse
    
    groups = defaultdict(list)
    for f in findings:
        fingerprint = compute_finding_fingerprint(f)
        groups[fingerprint].append(f)

    deduped = []
    for group in groups.values():
        # Choose highest severity (and if tie, highest confidence)
        best = max(group, key=lambda x: (severity_rank(x.severity), getattr(x, 'confidence', 0.5)))
        # Merge evidence from all duplicates
        merged_evidence = {}
        for g in group:
            merged_evidence.update(g.evidence or {})
        best.evidence = merged_evidence
        # Track all finding IDs that were deduplicated
        best.deduplicated_from = [g.finding_id for g in group if g.finding_id != best.finding_id]
        best.deduplication_count = len(group)
        deduped.append(best)
    return deduped


def compute_finding_confidence(finding: Finding, evidence: Dict[str, Any], 
                              validator_id: str) -> float:
    """
    Compute confidence score for a finding based on evidence quality.
    
    Returns a value between 0.0 and 1.0.
    """
    confidence = 0.5  # base confidence
    
    # Base confidence by validator type
    validator_confidence = {
        "https_validator": 0.8,
        "security_headers_validator": 0.7,
        "cookie_security_validator": 0.75,
        "information_disclosure_validator": 0.6,
        "redirect_validator": 0.8,
        "tls_validator": 0.85,
        "input_validation_validator": 0.7,
        "security_header_behavior_validator": 0.75,
        "access_control_validator": 0.8,
        "session_management_validator": 0.7,
        "error_disclosure_validator": 0.8,
        "security_headers_validator": 0.7,
        "cookie_security_validator": 0.75,
        "information_disclosure_validator": 0.6,
        "redirect_validator": 0.8,
        "tls_validator": 0.85,
    }
    
    confidence = validator_confidence.get(validator_id, 0.5)
    
    # Adjust based on evidence quality
    if hasattr(finding, 'evidence') and finding.evidence:
        # More evidence = higher confidence
        evidence_count = len(finding.evidence) if isinstance(finding.evidence, dict) else 1
        confidence += min(0.1 * evidence_count, 0.2)
        
        # Direct evidence (status codes, headers) increases confidence
        if isinstance(finding.evidence, dict):
            if 'status' in finding.evidence:
                confidence += 0.05
            if 'header' in finding.evidence or 'headers' in finding.evidence:
                confidence += 0.05
            if 'content_preview' in finding.evidence or 'match' in finding.evidence:
                confidence += 0.05
    
    # Adjust for finding state
    if hasattr(finding, 'metadata') and finding.metadata:
        state = finding.metadata.get('verification_state')
        if state == 'verified':
            confidence += 0.1
        elif state == 'rejected':
            confidence = max(0.1, confidence - 0.2)
        elif state == 'inconclusive':
            confidence = min(confidence, 0.5)
        elif state == 'rejected':
            confidence = max(0.1, confidence - 0.3)
    
    # Cap at 1.0
    return min(max(confidence, 0.0), 1.0)


def calculate_finding_severity(finding: Finding, evidence: Dict[str, Any],
                               validator_id: str) -> str:
    """
    Calculate severity based on finding type and evidence.
    """
    # Base severity by category
    category_severity = {
        "TLS": "High",
        "TLSConfiguration": "High",
        "TransportSecurity": "High",
        "ScopeViolation": "High",
        "NetworkSafety": "High",
        "AccessControl": "High",
        "TransportSecurity": "High",
        "CookieSecurity": "Medium",
        "SecurityHeaders": "Medium",
        "InformationDisclosure": "Low",
        "Redirect": "Medium",
        "Availability": "Low",
        "CookieSecurity": "Medium",
        "CookieSecurity": "Medium",
        "InformationDisclosure": "Low",
        "Redirect": "Medium",
        "Availability": "Low",
        "ValidatorError": "High",
        "Availability": "Low",
        "TransportSecurity": "Medium",
        "CookieSecurity": "Medium",
    }
    
    base_severity = category_severity.get(finding.category, "Informational")
    
    # Adjust based on evidence
    if hasattr(finding, 'evidence') and finding.evidence:
        evidence_str = str(finding.evidence).lower()
        # Escalate for certain evidence patterns
        if any(kw in str(finding.evidence).lower() for kw in 
               ['password', 'secret', 'token', 'secret', 'credential']):
            # Escalate severity for secret exposure
            severity_order = ["Informational", "Low", "Medium", "High", "Critical"]
            current_idx = severity_order.index(base_severity)
            base_severity = severity_order[min(current_idx + 2, len(severity_order) - 1)]
        elif any(kw in str(finding.evidence).lower() for kw in 
                ['stack trace', 'traceback', 'exception', 'internal server error']):
            severity_order = ["Informational", "Low", "Medium", "High", "Critical"]
            current_idx = severity_order.index(base_severity)
            base_severity = severity_order[min(current_idx + 1, len(severity_order) - 1)]
    
    return base_severity


def classify_findings(findings: List[Finding]) -> List[Finding]:
    """
    Deduplicate findings using stable fingerprints.
    
    Groups findings by stable fingerprint and keeps the one with highest severity.
    Merges evidence from all duplicates.
    """
    from urllib.parse import urlparse
    
    groups = defaultdict(list)
    for f in findings:
        fingerprint = compute_finding_fingerprint(f)
        groups[fingerprint].append(f)

    deduped = []
    for group in groups.values():
        # Choose highest severity (and if tie, highest confidence)
        best = max(group, key=lambda x: (severity_rank(x.severity), getattr(x, 'confidence', 0.5)))
        # Merge evidence from all duplicates
        merged_evidence = {}
        for g in group:
            merged_evidence.update(g.evidence or {})
        best.evidence = merged_evidence
        # Track all finding IDs that were deduplicated
        best.deduplicated_from = [g.finding_id for g in group if g.finding_id != best.finding_id]
        best.deduplication_count = len(group)
        deduped.append(best)
    return deduped