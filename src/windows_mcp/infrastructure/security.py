"""IP allowlist middleware and parsing for inbound HTTP requests."""

from __future__ import annotations

import ipaddress

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp


def _normalize_ip_address(ip: ipaddress._BaseAddress) -> ipaddress._BaseAddress:
    """Unwrap IPv4-mapped IPv6 addresses (e.g. ``::ffff:192.168.1.5`` -> ``192.168.1.5``).

    On dual-stack listeners (such as ``--host ::``), IPv4 clients arrive as
    IPv4-mapped IPv6 addresses, which do not match ``IPv4Network`` allowlist entries.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _normalize_ip_network(net: ipaddress._BaseNetwork) -> ipaddress._BaseNetwork:
    """Unwrap IPv4-mapped IPv6 CIDRs (within ``::ffff:0:0/96``) to IPv4 networks."""
    if (
        isinstance(net, ipaddress.IPv6Network)
        and net.prefixlen >= 96
        and net.network_address.ipv4_mapped is not None
    ):
        return ipaddress.IPv4Network((net.network_address.ipv4_mapped, net.prefixlen - 96))
    return net


def parse_ip_allowlist(raw_entries: list[str]) -> list[ipaddress._BaseNetwork]:
    """Parse a list of IP addresses and CIDR ranges into network objects.

    Accepts individual IPs (e.g. '192.168.1.5') and CIDR ranges
    (e.g. '10.0.0.0/8', '2001:db8::/32'). Raises ValueError on invalid entries.
    """
    parsed: list[ipaddress._BaseNetwork] = []
    errors: list[str] = []

    for entry in raw_entries:
        value = entry.strip()
        if not value:
            continue
        try:
            if "/" in value:
                net = ipaddress.ip_network(value, strict=False)
            else:
                ip = _normalize_ip_address(ipaddress.ip_address(value))
                suffix = "/32" if ip.version == 4 else "/128"
                net = ipaddress.ip_network(f"{ip}{suffix}", strict=False)
            parsed.append(_normalize_ip_network(net))
        except ValueError as exc:
            errors.append(f"{entry!r}: {exc}")

    if errors:
        raise ValueError("Invalid IP allowlist entries: " + "; ".join(errors))

    return parsed


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    """Restrict inbound connections to a configured set of IP networks (CIDR supported)."""

    def __init__(self, app: ASGIApp, *, allowlist: list[ipaddress._BaseNetwork]) -> None:
        super().__init__(app)
        self.allowlist = [_normalize_ip_network(net) for net in allowlist]

    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)

        client = request.client
        if client is None:
            return JSONResponse({"error": "Forbidden: missing client address"}, status_code=403)

        try:
            client_ip = _normalize_ip_address(ipaddress.ip_address(client.host))
        except ValueError:
            return JSONResponse(
                {"error": f"Forbidden: invalid client address '{client.host}'"}, status_code=403
            )

        if not any(client_ip in net for net in self.allowlist):
            return JSONResponse(
                {"error": f"Forbidden: {client_ip} is not in the IP allowlist"}, status_code=403
            )

        return await call_next(request)
