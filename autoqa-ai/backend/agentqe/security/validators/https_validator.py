"""
HTTPS validator – ensures the target uses HTTPS (or HTTP only when policy allows).
"""
from __future__ import annotations

from typing import List

import requests

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext
from agentqe.security.security_config import CONFIG


class HTTPSValidator(BaseValidator):
    validator_id = "https_validator"
    name = "HTTPS Enforcement"
    description = "Checks that the target is reachable over HTTPS and that HTTP redirects to HTTPS."

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []
        target = ctx.normalized_target

        # If policy already disallows HTTP, any HTTP scheme is a finding
        parsed = requests.utils.urlparse(target)
        if parsed.scheme == "http":
            if not CONFIG.allow_http:
                findings.append(Finding(
                    finding_id=f"{self.validator_id}-http",
                    category="TransportSecurity",
                    severity="Medium",
                    description="Target is accessible via plain HTTP while policy requires HTTPS.",
                    evidence={"url": target, "scheme": "http"},
                    source=self.validator_id,
                ))
            else:
                # HTTP allowed by policy – informational
                findings.append(Finding(
                    finding_id=f"{self.validator_id}-http-allowed",
                    category="TransportSecurity",
                    severity="Informational",
                    description="Target reachable via HTTP (policy permits HTTP).",
                    evidence={"url": target},
                    source=self.validator_id,
                ))

        # Try HTTPS request (HEAD) to verify TLS handshake works
        https_url = target
        if parsed.scheme != "https":
            https_url = target.replace("http://", "https://", 1)

        try:
            resp = requests.head(https_url, timeout=5, allow_redirects=True, verify=True)
            if resp.url.startswith("http://"):
                findings.append(Finding(
                    finding_id=f"{self.validator_id}-downgrade",
                    category="TransportSecurity",
                    severity="High",
                    description="HTTPS request was downgraded to HTTP via redirect.",
                    evidence={"final_url": resp.url},
                    source=self.validator_id,
                ))
        except requests.exceptions.SSLError as exc:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-tls-error",
                category="TransportSecurity",
                severity="High",
                description=f"TLS handshake failed: {exc}",
                evidence={"url": https_url, "error": str(exc)},
                source=self.validator_id,
            ))
        except requests.RequestException as exc:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-unreachable",
                category="Availability",
                severity="Low",
                description=f"HTTPS endpoint unreachable: {exc}",
                evidence={"url": https_url, "error": str(exc)},
                source=self.validator_id,
            ))

        return findings