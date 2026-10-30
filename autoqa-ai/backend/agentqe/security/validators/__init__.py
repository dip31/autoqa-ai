"""
Validators package – imports concrete validators and registers them.
"""
from __future__ import annotations

from agentqe.security.validators.https_validator import HTTPSValidator
from agentqe.security.validators.security_headers_validator import SecurityHeadersValidator
from agentqe.security.validators.cookie_security_validator import CookieSecurityValidator
from agentqe.security.validators.information_disclosure_validator import InformationDisclosureValidator
from agentqe.security.validators.redirect_validator import RedirectValidator
from agentqe.security.validators.tls_validator import TLSValidator
# Phase 5B: Active validators
from agentqe.security.validators.input_validation_validator import InputValidationValidator
from agentqe.security.validators.security_header_behavior_validator import SecurityHeaderBehaviorValidator
from agentqe.security.validators.access_control_validator import AccessControlValidator
from agentqe.security.validators.session_management_validator import SessionManagementValidator
from agentqe.security.validators.error_disclosure_validator import ErrorDisclosureValidator
from agentqe.security.validators.base import register_validator

# Instantiate and register
_registered = []

def _register_all():
    global _registered
    validators = [
        HTTPSValidator(),
        SecurityHeadersValidator(),
        CookieSecurityValidator(),
        InformationDisclosureValidator(),
        RedirectValidator(),
        TLSValidator(),
        # Phase 5B: Active validators
        InputValidationValidator(),
        SecurityHeaderBehaviorValidator(),
        AccessControlValidator(),
        SessionManagementValidator(),
        ErrorDisclosureValidator(),
    ]
    for v in validators:
        register_validator(v)
        _registered.append(v)

_register_all()

# Module names for dynamic import (snake_case, matching file names)
_validator_modules = [
    "https_validator",
    "security_headers_validator",
    "cookie_security_validator",
    "information_disclosure_validator",
    "redirect_validator",
    "tls_validator",
    # Phase 5B: Active validators
    "input_validation_validator",
    "security_header_behavior_validator",
    "access_control_validator",
    "session_management_validator",
    "error_disclosure_validator",
]

# Mapping from module name to class name for dynamic import
_validator_class_names = {
    "https_validator": "HTTPSValidator",
    "security_headers_validator": "SecurityHeadersValidator",
    "cookie_security_validator": "CookieSecurityValidator",
    "information_disclosure_validator": "InformationDisclosureValidator",
    "redirect_validator": "RedirectValidator",
    "tls_validator": "TLSValidator",
    # Phase 5B: Active validators
    "input_validation_validator": "InputValidationValidator",
    "security_header_behavior_validator": "SecurityHeaderBehaviorValidator",
    "access_control_validator": "AccessControlValidator",
    "session_management_validator": "SessionManagementValidator",
    "error_disclosure_validator": "ErrorDisclosureValidator",
}

__all__ = [
    "HTTPSValidator",
    "SecurityHeadersValidator",
    "CookieSecurityValidator",
    "InformationDisclosureValidator",
    "RedirectValidator",
    "TLSValidator",
    # Phase 5B: Active validators
    "InputValidationValidator",
    "SecurityHeaderBehaviorValidator",
    "AccessControlValidator",
    "SessionManagementValidator",
    "ErrorDisclosureValidator",
]