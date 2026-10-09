"""Try local authenticated subject discovery against real public providers."""

from __future__ import annotations

import argparse
import getpass
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def request_json(
    url: str,
    token: str | None = None,
    body: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers)
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--query", required=True)
    parser.add_argument("--level", default="middle_school")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        auth = request_json(
            f"{base_url}/api/auth/login",
            body={"username": username, "password": password},
        )
        result = request_json(
            f"{base_url}/api/discovery/search?{urlencode({'q': args.query, 'level': args.level})}",
            token=auth["token"],
        )
    except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Discovery request failed: {exc}") from exc

    if result.get("message"):
        print(result["message"])
    for index, candidate in enumerate(result.get("results", []), start=1):
        print(f"\n{index}. {candidate['name']} ({candidate['source']})")
        print(candidate["summary"])
        print(f"Confidence: {candidate['confidence']:.0%}")
        print(f"Source: {candidate['source_url']}")


if __name__ == "__main__":
    main()
