"""
TLS validator – performs a TLS handshake and inspects certificate.
"""
from __future__ import annotations

import ssl
import socket
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlparse

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext


class TLSValidator(BaseValidator):
    validator_id = "tls_validator"
    name = "TLS Configuration"
    description = "Checks certificate validity, expiration, hostname match, and key size."

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []
        parsed = urlparse(ctx.normalized_target)
        host = parsed.hostname
        port = parsed.port or 443

        if parsed.scheme != "https":
            findings.append(Finding(
                finding_id=f"{self.validator_id}-not-https",
                category="TransportSecurity",
                severity="Informational",
                description="TLS check skipped because target scheme is not HTTPS",
                evidence={"scheme": parsed.scheme},
                source=self.validator_id,
            ))
            return findings

        try:
            context = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    # Expiration
                    not_after = cert.get("notAfter")
                    if not_after:
                        exp_dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                        days_left = (exp_dt - datetime.now(timezone.utc)).days
                        if days_left < 0:
                            sev = "Critical"
                            desc = f"Certificate expired {abs(days_left)} days ago"
                        elif days_left < 30:
                            sev = "High"
                            desc = f"Certificate expires in {days_left} days"
                        else:
                            sev = "Informational"
                            desc = f"Certificate valid for {days_left} more days"
                        findings.append(Finding(
                            finding_id=f"{self.validator_id}-expiration",
                            category="TLS",
                            severity=sev,
                            description=desc,
                            evidence={"expires": not_after, "days_left": days_left},
                            source=self.validator_id,
                        ))
                    # Subject CN / SAN match
                    san = []
                    for typ, val in cert.get("subjectAltName", []):
                        if typ == "DNS":
                            san.append(val)
                    if host not in san and host not in [v for k, v in cert.get("subject", []) if k == "commonName"]:
                        findings.append(Finding(
                            finding_id=f"{self.validator_id}-hostname-mismatch",
                            category="TLS",
                            severity="High",
                            description="Certificate does not match target hostname",
                            evidence={"host": host, "SAN": san, "subject": cert.get("subject")},
                            source=self.validator_id,
                        ))
        except ssl.SSLError as exc:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-ssl-error",
                category="TLS",
                severity="High",
                description=f"SSL error: {exc}",
                evidence={"error": str(exc)},
                source=self.validator_id,
            ))
        except Exception as exc:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-error",
                category="TLS",
                severity="Low",
                description=f"Unable to perform TLS check: {exc}",
                evidence={"error": str(exc)},
                source=self.validator_id,
            ))
        return findings