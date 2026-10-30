"""
Cookie‑security validator – inspects Set‑Cookie headers for Secure, HttpOnly, SameSite.
"""
from __future__ import annotations

import re
from typing import List

import requests

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext


class CookieSecurityValidator(BaseValidator):
    validator_id = "cookie_security_validator"
    name = "Cookie Security"
    description = "Checks Secure, HttpOnly, SameSite attributes on cookies."

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []
        try:
            resp = requests.get(ctx.normalized_target, timeout=5, allow_redirects=True, verify=True)
        except requests.RequestException as exc:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-request-error",
                category="Availability",
                severity="Low",
                description=f"Unable to fetch cookies: {exc}",
                evidence={"error": str(exc)},
                source=self.validator_id,
            ))
            return findings

        cookie_header = resp.headers.get("Set-Cookie", "")
        if not cookie_header:
            # No cookies – informational
            findings.append(Finding(
                finding_id=f"{self.validator_id}-no-cookies",
                category="CookieSecurity",
                severity="Informational",
                description="No Set‑Cookie header observed.",
                evidence={"url": resp.url},
                source=self.validator_id,
            ))
            return findings

        # Split on commas that separate cookies (naïve but works for simple cases)
        cookies = re.split(r'(?<=; ),', cookie_header)  # split on ', ' after a semicolon
        for idx, cookie in enumerate(cookies):
            name_match = re.match(r'^([^=]+)=', cookie)
            cookie_name = name_match.group(1) if name_match else f"cookie_{idx}"
            low = cookie.lower()
            issues = []
            if "secure" not in low:
                issues.append("Missing Secure flag")
            if "httponly" not in low:
                issues.append("Missing HttpOnly flag")
            if "samesite" not in low:
                issues.append("Missing SameSite attribute")
            elif not re.search(r'samesite=(strict|lax|none)', low):
                issues.append("SameSite value not Strict/Lax/None")

            for issue in issues:
                findings.append(Finding(
                    finding_id=f"{self.validator_id}-{cookie_name}-{issue.replace(' ', '_').lower()}",
                    category="CookieSecurity",
                    severity="Medium" if "Secure" in issue else "Low",
                    description=f"Cookie '{cookie_name}': {issue}",
                    evidence={"cookie": cookie[:200], "url": resp.url},
                    source=self.validator_id,
                ))
        return findings