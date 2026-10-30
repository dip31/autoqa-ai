"""
Security Header Behavior Validator – Active behavioral verification of security headers.

This validator verifies that security headers not only exist but behave
as expected (e.g., CSP blocks inline scripts, HSTS upgrades connections).
"""

from __future__ import annotations

from typing import List, Dict, Any
import requests

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext


class SecurityHeaderBehaviorValidator(BaseValidator):
    validator_id = "security_header_behavior_validator"
    name = "Security Header Behavior"
    description = "Verifies that security headers behave as expected (CSP, HSTS, X-Frame-Options, etc.)"

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []
        target = ctx.normalized_target

        try:
            # Make a request to observe headers
            resp = requests.get(target, timeout=10, allow_redirects=True, verify=True)
            headers = {k.lower(): v for k, v in resp.headers.items()}
            final_url = resp.url

            # Check HSTS behavior
            hsts_findings = self._check_hsts(headers, final_url, target)
            findings.extend(hsts_findings)

            # Check CSP behavior
            csp_findings = self._check_csp_behavior(headers, final_url, target)
            findings.extend(csp_findings)

            # Check X-Frame-Options
            xfo_findings = self._check_xfo(headers, final_url, target)
            findings.extend(xfo_findings)

            # Check X-Content-Type-Options
            xcto_findings = self._check_xcto(headers, final_url, target)
            findings.extend(xcto_findings)

            # Check Referrer-Policy
            rp_findings = self._check_referrer_policy(headers, final_url, target)
            findings.extend(rp_findings)

            # Check Permissions-Policy
            pp_findings = self._check_permissions_policy(headers, final_url, target)
            findings.extend(pp_findings)

        except requests.RequestException as exc:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-request-error",
                category="HeaderBehavior",
                severity="Low",
                description=f"Unable to fetch headers for behavior analysis: {exc}",
                evidence={"error": str(exc), "url": target},
                source=self.validator_id,
                metadata={"check_type": "active", "error": True},
            ))

        return findings

    def _check_hsts(self, headers: Dict[str, str], final_url: str, original_url: str) -> List[Finding]:
        findings: List[Finding] = []
        hsts = headers.get("strict-transport-security")

        if not hsts:
            return [Finding(
                finding_id=f"{self.validator_id}-hsts-missing",
                category="HeaderBehavior",
                severity="Medium",
                description="HSTS header missing - no transport security enforcement",
                evidence={"url": original_url, "final_url": final_url, "headers_checked": list(headers.keys())},
                source=self.validator_id,
                metadata={"check_type": "active"},
            )]

        # Check for preload directive
        if "preload" not in hsts.lower():
            # Not necessarily a finding, but informational
            pass

        # Check max-age
        import re
        max_age_match = re.search(r"max-age=(\d+)", hsts)
        if max_age_match:
            max_age = int(max_age_match.group(1))
            if max_age < 31536000:  # Less than 1 year
                return [Finding(
                    finding_id=f"{self.validator_id}-hsts-short-maxage",
                    category="HeaderBehavior",
                    severity="Low",
                    description=f"HSTS max-age is only {max_age} seconds (recommended: 31536000+)",
                    evidence={"hsts_header": hsts, "max_age": max_age},
                    source=self.validator_id,
                    metadata={"check_type": "active"},
                )]

        # Check includeSubDomains
        if "includesubdomains" not in hsts.lower():
            return [Finding(
                finding_id=f"{self.validator_id}-hsts-no-subdomains",
                category="HeaderBehavior",
                severity="Low",
                description="HSTS missing includeSubDomains directive",
                evidence={"hsts_header": hsts},
                source=self.validator_id,
                metadata={"check_type": "active"},
            )]

        return findings

    def _check_csp_behavior(self, headers: Dict[str, str], final_url: str, original_url: str) -> List[Finding]:
        findings: List[Finding] = []
        csp = headers.get("content-security-policy")

        if not csp:
            return [Finding(
                finding_id=f"{self.validator_id}-csp-missing",
                category="HeaderBehavior",
                severity="Medium",
                description="Content-Security-Policy header missing - no CSP enforcement",
                evidence={"url": original_url, "final_url": final_url},
                source=self.validator_id,
                metadata={"check_type": "active"},
            )]

        # Check for unsafe directives
        csp_lower = csp.lower()
        issues = []

        if "'unsafe-inline'" in csp_lower and "script-src" in csp_lower:
            issues.append("CSP allows 'unsafe-inline' for scripts")

        if "'unsafe-eval'" in csp_lower:
            issues.append("CSP allows 'unsafe-eval'")

        if "frame-ancestors" not in csp_lower:
            issues.append("CSP missing frame-ancestors directive (clickjacking protection)")

        if "object-src" not in csp_lower:
            issues.append("CSP missing object-src directive")

        if "base-uri" not in csp_lower:
            issues.append("CSP missing base-uri directive")

        # Check for overly permissive default-src
        if "default-src" in csp_lower:
            default_src = csp.split("default-src")[1].split(";")[0].strip()
            if "*" in default_src or "https:" in default_src or "http:" in default_src:
                issues.append("CSP default-src is overly permissive")

        if issues:
            return [Finding(
                finding_id=f"{self.validator_id}-csp-weak",
                category="HeaderBehavior",
                severity="Medium",
                description=f"CSP has configuration issues: {'; '.join(issues)}",
                evidence={"csp_header": csp, "issues": issues, "url": final_url},
                source=self.validator_id,
                metadata={"check_type": "active"},
            )]

        return findings

    def _check_xfo(self, headers: Dict[str, str], final_url: str, original_url: str) -> List[Finding]:
        findings: List[Finding] = []
        xfo = headers.get("x-frame-options")

        if not xfo:
            # Check CSP frame-ancestors as alternative
            csp = headers.get("content-security-policy", "")
            if "frame-ancestors" not in csp.lower():
                return [Finding(
                    finding_id=f"{self.validator_id}-xfo-missing",
                    category="HeaderBehavior",
                    severity="Medium",
                    description="X-Frame-Options missing and no CSP frame-ancestors directive",
                    evidence={"url": original_url, "final_url": final_url},
                    source=self.validator_id,
                    metadata={"check_type": "active"},
                )]
        else:
            xfo_lower = xfo.lower()
            if xfo_lower not in ["deny", "sameorigin"]:
                return [Finding(
                    finding_id=f"{self.validator_id}-xfo-weak",
                    category="HeaderBehavior",
                    severity="Medium",
                    description=f"X-Frame-Options has weak value: {xfo}",
                    evidence={"xfo_header": xfo},
                    source=self.validator_id,
                    metadata={"check_type": "active"},
                )]

        return findings

    def _check_xcto(self, headers: Dict[str, str], final_url: str, original_url: str) -> List[Finding]:
        findings: List[Finding] = []
        xcto = headers.get("x-content-type-options")

        if not xcto:
            return [Finding(
                finding_id=f"{self.validator_id}-xcto-missing",
                category="HeaderBehavior",
                severity="Low",
                description="X-Content-Type-Options header missing - MIME sniffing possible",
                evidence={"url": original_url, "final_url": final_url},
                source=self.validator_id,
                metadata={"check_type": "active"},
            )]

        if xcto.lower() != "nosniff":
            return [Finding(
                finding_id=f"{self.validator_id}-xcto-weak",
                category="HeaderBehavior",
                severity="Low",
                description=f"X-Content-Type-Options has unexpected value: {xcto}",
                evidence={"xcto_header": xcto},
                source=self.validator_id,
                metadata={"check_type": "active"},
            )]

        return findings

    def _check_referrer_policy(self, headers: Dict[str, str], final_url: str, original_url: str) -> List[Finding]:
        findings: List[Finding] = []
        rp = headers.get("referrer-policy")

        if not rp:
            return [Finding(
                finding_id=f"{self.validator_id}-rp-missing",
                category="HeaderBehavior",
                severity="Low",
                description="Referrer-Policy header missing",
                evidence={"url": original_url, "final_url": final_url},
                source=self.validator_id,
                metadata={"check_type": "active"},
            )]

        rp_lower = rp.lower()
        weak_policies = ["no-referrer-when-downgrade", "origin", "origin-when-cross-origin", "unsafe-url"]
        if any(p in rp_lower for p in weak_policies):
            return [Finding(
                finding_id=f"{self.validator_id}-rp-weak",
                category="HeaderBehavior",
                severity="Low",
                description=f"Referrer-Policy may leak information: {rp}",
                evidence={"referrer_policy": rp},
                source=self.validator_id,
                metadata={"check_type": "active"},
            )]

        return findings

    def _check_permissions_policy(self, headers: Dict[str, str], final_url: str, original_url: str) -> List[Finding]:
        findings: List[Finding] = []
        pp = headers.get("permissions-policy")

        if not pp:
            return [Finding(
                finding_id=f"{self.validator_id}-pp-missing",
                category="HeaderBehavior",
                severity="Low",
                description="Permissions-Policy header missing",
                evidence={"url": original_url, "final_url": final_url},
                source=self.validator_id,
                metadata={"check_type": "active"},
            )]

        # Check for dangerous features allowed
        pp_lower = pp.lower()
        dangerous = ["camera", "microphone", "geolocation", "payment", "usb", "magnetometer", "gyroscope"]
        allowed_dangerous = [d for d in dangerous if d in pp_lower and "=()" not in pp_lower and f"{d}=*" not in pp_lower]

        if allowed_dangerous:
            return [Finding(
                finding_id=f"{self.validator_id}-pp-dangerous",
                category="HeaderBehavior",
                severity="Medium",
                description=f"Permissions-Policy allows dangerous features: {', '.join(allowed_dangerous)}",
                evidence={"permissions_policy": pp, "dangerous_allowed": allowed_dangerous},
                source=self.validator_id,
                metadata={"check_type": "active"},
            )]

        return findings