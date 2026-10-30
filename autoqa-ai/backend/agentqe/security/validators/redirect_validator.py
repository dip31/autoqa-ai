"""
Redirect validator – analyses redirect chain for scope violations and excessive length.
"""
from __future__ import annotations

from typing import List

import requests

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext
from agentqe.security.scope_validator import validate_url_scope, ScopeDefinition
from agentqe.security.network_safety import classify_ip_address


class RedirectValidator(BaseValidator):
    validator_id = "redirect_validator"
    name = "Redirect Analysis"
    description = "Follows redirect chain, validates each hop against approved scope and network policy."

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []
        scope_def = ScopeDefinition(
            scheme=ctx.scope.get("scheme", "https"),
            host=ctx.scope.get("host", ""),
            port=ctx.scope.get("port"),
            path_prefix=ctx.scope.get("path_prefix", "/"),
            allow_subdomains=ctx.scope.get("allow_subdomains", False),
        )

        # Use requests with allow_redirects=False to capture chain manually
        url = ctx.normalized_target
        visited = []
        max_hops = 10
        for hop in range(max_hops):
            try:
                resp = requests.get(url, timeout=5, allow_redirects=False, verify=True)
            except requests.RequestException as exc:
                findings.append(Finding(
                    finding_id=f"{self.validator_id}-request-error",
                    category="Availability",
                    severity="Low",
                    description=f"Redirect chain interrupted: {exc}",
                    evidence={"url": url, "error": str(exc)},
                    source=self.validator_id,
                ))
                break

            visited.append({"url": url, "status": resp.status_code})
            if 300 <= resp.status_code < 400:
                location = resp.headers.get("Location")
                if not location:
                    findings.append(Finding(
                        finding_id=f"{self.validator_id}-missing-location",
                        category="Redirect",
                        severity="Low",
                        description="Redirect response missing Location header",
                        evidence={"url": url, "status": resp.status_code},
                        source=self.validator_id,
                    ))
                    break
                # Resolve absolute URL
                next_url = requests.compat.urljoin(url, location)

                # Scope validation
                scope_res = validate_url_scope(next_url, scope_def)
                if not scope_res.allowed:
                    findings.append(Finding(
                        finding_id=f"{self.validator_id}-out-of-scope",
                        category="ScopeViolation",
                        severity="High",
                        description=f"Redirect leads outside approved scope: {scope_res.message}",
                        evidence={"from": url, "to": next_url, "reason": scope_res.reason_code},
                        source=self.validator_id,
                    ))
                    # Still continue to see further hops? stop to avoid leaving scope
                    break

                # Network safety – resolve host and check IP
                from urllib.parse import urlparse
                parsed = urlparse(next_url)
                host = parsed.hostname or ""
                # quick DNS resolve via socket (reuse network_safety.resolve_hostname would need mock)
                import socket
                try:
                    infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
                    for _fam, _type, _proto, _canon, sockaddr in infos:
                        ip = sockaddr[0]
                        allowed, reason = classify_ip_address(ip)
                        if not allowed:
                            findings.append(Finding(
                                finding_id=f"{self.validator_id}-prohibited-ip",
                                category="NetworkSafety",
                                severity="High",
                                description=f"Redirect resolves to prohibited IP {ip} ({reason})",
                                evidence={"url": next_url, "ip": ip, "reason": reason},
                                source=self.validator_id,
                            ))
                except socket.gaierror:
                    pass

                url = next_url
                continue
            else:
                # No more redirects
                break

        if len(visited) > 5:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-long-chain",
                category="Redirect",
                severity="Medium",
                description=f"Redirect chain length {len(visited)} exceeds recommended limit",
                evidence={"chain": visited},
                source=self.validator_id,
            ))
        return findings