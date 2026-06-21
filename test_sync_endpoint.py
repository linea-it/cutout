#!/usr/bin/env python3
"""Smoke test for the sync cutout endpoint using token authentication.

Examples:
    python test_sync_endpoint.py \
    --username agent_tester \
    --password secret \
        --engine astrocut \
        --pos "CIRCLE 36.30911 -10.18749 0.01" \
        --output /tmp/sync_astrocut_result.fits

  python test_sync_endpoint.py \
    --username agent_tester \
        --password secret \
        --engine legacy \
        --pos "CIRCLE 36.30911 -10.18749 0.01" \
        --output /tmp/sync_legacy_result.fits

    python test_sync_endpoint.py \
        --username agent_tester \
        --password secret \
        --id private_survey \
        --engine astrocut
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def get_token(base_url: str, username: str, password: str) -> str:
    url = f"{base_url.rstrip('/')}/auth-token/"
    payload = json.dumps({"username": username, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    token = data.get("token")
    if not token:
        raise RuntimeError(f"Token not found in auth response: {body}")
    return token


def call_sync(
    *,
    base_url: str,
    token: str,
    survey_id: str,
    pos: str,
    engine: str,
    output_format: str,
    band: str,
) -> tuple[int, str, bytes]:
    query = urllib.parse.urlencode(
        {
            "id": survey_id,
            "pos": pos,
            "engine": engine,
            "format": output_format,
            "band": band,
        }
    )
    url = f"{base_url.rstrip('/')}/api/sync?{query}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Token {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        status = resp.getcode()
        content_type = resp.headers.get("Content-Type", "")
        body = resp.read()
    return status, content_type, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Test /api/sync endpoint")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--username", required=True, help="Django username")
    parser.add_argument("--password", required=True, help="Django password")
    parser.add_argument("--id", default="des_dr2", dest="survey_id", help="Survey ID")
    parser.add_argument("--pos", default="CIRCLE 36.30911 -10.18749 2", help="POS value")
    parser.add_argument("--engine", default="astrocut", help="Engine name: astrocut or legacy")
    parser.add_argument("--format", default="fits", dest="output_format", help="Output format")
    parser.add_argument("--band", default="g", help="Band")
    parser.add_argument(
        "--output",
        default="/tmp/sync_result_test.fits",
        help="Output file path for successful binary response",
    )
    args = parser.parse_args()

    try:
        token = get_token(args.base_url, args.username, args.password)
        print("auth: ok")

        status, content_type, body = call_sync(
            base_url=args.base_url,
            token=token,
            survey_id=args.survey_id,
            pos=args.pos,
            engine=args.engine,
            output_format=args.output_format,
            band=args.band,
        )
        print(f"status: {status}")
        print(f"content-type: {content_type}")

        if status == 200 and "application/json" not in content_type:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(body)
            print(f"result saved to: {output}")
        else:
            text = body.decode("utf-8", errors="replace")
            print("response body:")
            print(text[:2000])

        return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"http error: {e.code}")
        print(body[:2000])
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
