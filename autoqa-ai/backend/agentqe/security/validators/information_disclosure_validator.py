"""
Information‑disclosure validator – looks for common low‑impact disclosures.
"""
from __future__ import annotations

import re
from typing import List

import requests

from agentqe.interfaces import Finding
from agentqe.security.validators.base import BaseValidator, ValidationContext


class InformationDisclosureValidator(BaseValidator):
    validator_id = "information_disclosure_validator"
    name = "Information Disclosure"
    description = "Detects server/framework version headers, debug endpoints, and source‑map references."

    # Patterns to flag (header name regex -> (severity, description))
    HEADER_PATTERNS = [
        (r"^server$", ("Low", "Server header reveals software version")),
        (r"^x-powered-by$", ("Low", "X‑Powered‑By header reveals framework")),
        (r"^x-aspnet-version$", ("Low", "X‑AspNet‑Version header reveals ASP.NET version")),
        (r"^x-generator$", ("Low", "X‑Generator header reveals CMS version")),
    ]

    BODY_PATTERNS = [
        (r"<!--.*?-->", ("Informational", "HTML comment may leak internal paths")),
        (r"sourceMappingURL", ("Low", "JavaScript source map reference exposed")),
    ]

    def check(self, ctx: ValidationContext) -> List[Finding]:
        findings: List[Finding] = []
        try:
            resp = requests.get(ctx.normalized_target, timeout=5, allow_redirects=True, verify=True)
        except requests.RequestException as exc:
            findings.append(Finding(
                finding_id=f"{self.validator_id}-request-error",
                category="Availability",
                severity="Low",
                description=f"Unable to fetch response for disclosure check: {exc}",
                evidence={"error": str(exc)},
                source=self.validator_id,
            ))
            return findings

        # Header checks
        for hdr_name, hdr_val in resp.headers.items():
            for pattern, (sev, desc) in self.HEADER_PATTERNS:
                if re.match(pattern, hdr_name, re.IGNORECASE):
                    findings.append(Finding(
                        finding_id=f"{self.validator_id}-header-{hdr_name.lower()}",
                        category="InformationDisclosure",
                        severity=sev,
                        description=desc,
                        evidence={"header": hdr_name, "value": hdr_val[:200], "url": resp.url},
                        source=self.validator_id,
                    ))

        # Body checks (limit size)
        body = resp.text[:50000]
        for pattern, (sev, desc) in self.BODY_PATTERNS:
            for m in re.finditer(pattern, body, re.IGNORECASE | re.DOTALL):
                snippet = body[max(0, m.start()-50):m.end()+50]
                findings.append(Finding(
                    finding_id=f"{self.validator_id}-body-{pattern[:20]}",
                    category="InformationDisclosure",
                    severity=sev,
                    description=desc,
                    evidence={"match": snippet, "url": resp.url},
                    source=self.validator_id,
                ))
        return findings