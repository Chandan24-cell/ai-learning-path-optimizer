"""Network boundary for public discovery providers."""

from __future__ import annotations

import ipaddress
import json
import socket
import time
from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

ALLOWED_HOSTS = frozenset(
    {
        "en.wikipedia.org",
        "en.wikibooks.org",
        "www.wikidata.org",
        "openlibrary.org",
        "api.openalex.org",
        "openalex.org",
    }
)
MAX_RESPONSE_BYTES = 512 * 1024
REQUEST_TIMEOUT_SECONDS = 5
CACHE_TTL_SECONDS = 300
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_cache_lock = Lock()


class DiscoveryUnavailable(RuntimeError):
    """An allowed public discovery provider could not be reached safely."""


def validate_provider_url(url: str) -> str:
    parts = urlsplit(url)
    hostname = (parts.hostname or "").lower().rstrip(".")
    if (
        parts.scheme != "https"
        or hostname not in ALLOWED_HOSTS
        or parts.username is not None
        or parts.password is not None
        or parts.port not in (None, 443)
    ):
        raise ValueError("Only HTTPS URLs from approved discovery providers are allowed")
    return hostname


def _verify_public_dns(hostname: str) -> None:
    try:
        addresses = {
            info[4][0] for info in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }
        if not addresses or any(
            not ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise ValueError("Discovery provider resolved to a non-public IP address")
    except (OSError, ValueError) as exc:
        raise DiscoveryUnavailable("A discovery provider is offline or unsafe to contact") from exc


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def fetch_json(url: str) -> dict[str, Any]:
    hostname = validate_provider_url(url)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(url)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            _cache.move_to_end(url)
            return deepcopy(cached[1])
        if cached:
            del _cache[url]

    _verify_public_dns(hostname)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "LearningPath/1.0"})
    opener = build_opener(ProxyHandler({}), _NoRedirect)
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise DiscoveryUnavailable("A discovery provider returned an unexpected response")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise DiscoveryUnavailable("A discovery provider is temporarily unavailable") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise DiscoveryUnavailable("A discovery provider response exceeded the size limit")
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiscoveryUnavailable("A discovery provider returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise DiscoveryUnavailable("A discovery provider returned an invalid response")
    with _cache_lock:
        _cache[url] = (now, body)
        _cache.move_to_end(url)
        while len(_cache) > 128:
            _cache.popitem(last=False)
    return deepcopy(body)


def clear_cache() -> None:
    """Clear process-local provider response cache, primarily for isolated tests."""
    with _cache_lock:
        _cache.clear()
