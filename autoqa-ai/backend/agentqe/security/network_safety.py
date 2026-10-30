"""
Network safety utilities – IP address classification, DNS resolution, and
redirect‑time enforcement helpers.

All functions are pure and side‑effect free except for the DNS resolver which
performs a bounded lookup.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from typing import List, Tuple

from agentqe.security.security_config import CONFIG

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# IP address classification
# ----------------------------------------------------------------------
def _is_prohibited_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> Tuple[bool, str]:
    """
    Return (True, reason) if the IP address is prohibited by the current policy.
    """
    # Loopback
    if CONFIG.block_loopback and ip.is_loopback:
        return True, "LOOPBACK_ADDRESS"

    # Private / RFC1918 (IPv4) or Unique‑Local (IPv6)
    if CONFIG.block_private_ips and ip.is_private:
        return True, "PRIVATE_ADDRESS"

    # Link‑local
    if CONFIG.block_link_local and ip.is_link_local:
        return True, "LINK_LOCAL_ADDRESS"

    # Multicast
    if CONFIG.block_multicast and ip.is_multicast:
        return True, "MULTICAST_ADDRESS"

    # Reserved / unspecified / etc.
    if CONFIG.block_reserved and (ip.is_reserved or ip.is_unspecified):
        return True, "RESERVED_ADDRESS"

    # Cloud metadata IPv4 (169.254.169.254) and IPv6 equivalents
    if CONFIG.block_cloud_metadata:
        if isinstance(ip, ipaddress.IPv4Address) and ip == ipaddress.IPv4Address("169.254.169.254"):
            return True, "CLOUD_METADATA_ADDRESS"
        # IPv6 metadata addresses (e.g. fd00::/8 used by some clouds) – covered by private check

    return False, ""


def classify_ip_address(ip_str: str) -> Tuple[bool, str, ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """
    Parse an IP string and classify it.

    Returns (allowed, reason_code, ip_obj).  allowed=False means the address is
    prohibited; reason_code is a stable identifier for logging.
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError as exc:
        logger.warning("Network safety: invalid IP address string %s: %s", ip_str, exc)
        return False, "INVALID_IP_FORMAT", None  # type: ignore

    prohibited, reason = _is_prohibited_ip(ip_obj)
    if prohibited:
        logger.info("Network safety: prohibited IP %s (%s)", ip_obj, reason)
        return False, reason, ip_obj

    return True, "ALLOWED", ip_obj


# ----------------------------------------------------------------------
# DNS resolution with policy enforcement
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class DnsResult:
    hostname: str
    ips: List[ipaddress.IPv4Address | ipaddress.IPv6Address]
    allowed: bool
    reason_code: str


def resolve_hostname(hostname: str) -> DnsResult:
    """
    Resolve a hostname to all A/AAAA records and evaluate each address against
    the network policy.  The hostname is allowed only if *all* resolved addresses
    are permitted.
    """
    if not CONFIG.require_dns_validation:
        return DnsResult(hostname=hostname, ips=[], allowed=True, reason_code="DNS_VALIDATION_DISABLED")

    try:
        # Use getaddrinfo with AF_UNSPEC to get both IPv4 and IPv6
        infos = socket.getaddrinfo(
            hostname,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
            flags=socket.AI_ADDRCONFIG,
        )
    except socket.gaierror as exc:
        logger.warning("Network safety: DNS resolution failed for %s: %s", hostname, exc)
        return DnsResult(hostname=hostname, ips=[], allowed=False, reason_code="DNS_RESOLUTION_FAILED")

    # Extract unique IP addresses
    ips: List[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for _family, _type, _proto, _canon, sockaddr in infos:
        ip_str = sockaddr[0]
        # sockaddr may be IPv6 with scope id; strip scope
        if "%" in ip_str:
            ip_str = ip_str.split("%")[0]
        try:
            ips.append(ipaddress.ip_address(ip_str))
        except ValueError:
            continue

    if not ips:
        logger.warning("Network safety: DNS returned no IP addresses for %s", hostname)
        return DnsResult(hostname=hostname, ips=[], allowed=False, reason_code="DNS_NO_ADDRESSES")

    # Evaluate each address
    for ip_obj in ips:
        prohibited, reason = _is_prohibited_ip(ip_obj)
        if prohibited:
            logger.warning("Network safety: hostname %s resolves to prohibited IP %s (%s)", hostname, ip_obj, reason)
            return DnsResult(hostname=hostname, ips=ips, allowed=False, reason_code=reason)

    logger.debug("Network safety: hostname %s resolved to allowed IPs: %s", hostname, [str(i) for i in ips])
    return DnsResult(hostname=hostname, ips=ips, allowed=True, reason_code="DNS_OK")


# ----------------------------------------------------------------------
# Redirect safety helpers (used by browser request interception)
# ----------------------------------------------------------------------
def is_redirect_allowed(current_url: str, next_url: str, scope: "ScopeDefinition") -> Tuple[bool, str]:
    """
    Determine whether a redirect from current_url to next_url stays within the
    approved scope.  The check mirrors validate_url_scope but also ensures the
    scheme/host/port/path are still valid.
    """
    from agentqe.security.scope_validator import validate_url_scope, ScopeDefinition

    result = validate_url_scope(next_url, scope)
    return result.allowed, result.reason_code