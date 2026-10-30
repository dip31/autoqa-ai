"""
Security‑header validator – checks presence and basic quality of common HTTP security headers.
"""
from __future__ import annotations

from typing import List

import requests

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext


class SecurityHeadersValidator(BaseValidator):
    validator_id = "security_headers_validator"
    name = "Security Headers"
    description = "Inspects CSP, HSTS, X‑Content‑Type‑Options, Referrer‑Policy, Permissions‑Policy, X‑Frame‑Options."

    # Header name -> (severity if missing, description)
    HEADER_POLICY = {
        "Content-Security-Policy": ("Medium", "Missing Content‑Security‑Policy header"),
        "Strict-Transport-Security": ("Medium", "Missing HSTS header"),
        "X-Content-Type-Options": ("Low", "Missing X‑Content‑Type‑Options header"),
        "Referrer-Policy": ("Low", "Missing Referrer‑Policy header"),
        "Permissions-Policy": ("Low", "Missing Permissions‑Policy header"),
        "X-Frame-Options": ("Low", "Missing X‑Frame‑Options header"),
    }

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []
        # Perform a single GET to the normalized target (follow redirects)
        try:
            resp = requests.get(ctx.normalized_target, timeout=5, allow_redirects=True, verify=True)
        except requests.RequestException as exc:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-request-error",
                category="Availability",
                severity="Low",
                description=f"Unable to fetch headers: {exc}",
                evidence={"error": str(exc)},
                source=self.validator_id,
            ))
            return findings

        headers = {k.lower(): v for k, v in resp.headers.items()}

        for header, (sev, desc) in self.HEADER_POLICY.items():
            if header.lower() not in headers:
                findings.append(Finding(
                    finding_id=f"{self.validator_id}-missing-{header.lower()}",
                    category="SecurityHeaders",
                    severity=sev,
                    description=desc,
                    evidence={"header": header, "url": resp.url},
                    source=self.validator_id,
                ))
            else:
                # Optional: basic quality checks (e.g. HSTS max-age)
                val = headers[header.lower()]
                if header == "Strict-Transport-Security" and "max-age" not in val.lower():
                    findings.append(Finding(
                        finding_id=f"{self.validator_id}-weak-hsts",
                        category="SecurityHeaders",
                        severity="Low",
                        description="HSTS header present but lacks max‑age directive",
                        evidence={"header": header, "value": val},
                        source=self.validator_id,
                    ))
        return findings