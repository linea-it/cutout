#!/usr/bin/env python3
"""Smoke test for the sync cutout endpoint using token authentication.

Examples:
    python test_async_endpoint.py \
    --username agent_tester \
    --password secret \
        --engine astrocut \
        --pos "CIRCLE 36.30911 -10.18749 0.01" \
        --output /tmp/async_astrocut_result.fits

    python test_async_endpoint.py \
    --username agent_tester \
        --password secret \
        --engine legacy \
        --pos "CIRCLE 36.30911 -10.18749 0.01" \
        --output /tmp/async_legacy_result.fits

    python test_async_endpoint.py \
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


import time


def call_async_cutout(
    *,
    base_url: str,
    token: str,
    survey_id: str,
    pos: str,
    engine: str,
    output_format: str,
    band: str,
    poll_interval: float = 1.0,
    max_polls: int = 30,
) -> tuple[int, str, bytes]:
    # 1. Cria job async
    url = f"{base_url.rstrip('/')}/api/async"
    payload = json.dumps(
        {
            "id": survey_id,
            "pos": pos,
            "engine": engine,
            "format": output_format,
            "band": band,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Authorization": f"Token {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        status = resp.getcode()
        location = resp.headers.get("Location")
        body = resp.read()

    if status == 303 and location:
        job_url = location
        # print("Job created, polling at:", job_url)
    elif status == 200:
        # Fallback: resposta já é o JSON do job
        job_data = json.loads(body.decode("utf-8"))
        job_id = job_data.get("job_id")
        if not job_id:
            raise RuntimeError(f"No job_id in response: {body[:1000].decode('utf-8', 'replace')}")
        # Monta URL do job
        job_url = f"{base_url.rstrip('/')}/api/async/{job_id}"
    else:
        raise RuntimeError(
            f"Async job creation failed: status={status}, body={body[:1000].decode('utf-8', 'replace')}"
        )

    # 2. Poll job status
    for _ in range(max_polls):
        job_req = urllib.request.Request(
            job_url,
            headers={"Authorization": f"Token {token}"},
            method="GET",
        )
        with urllib.request.urlopen(job_req, timeout=20) as job_resp:
            job_data = json.loads(job_resp.read().decode("utf-8"))
        phase = job_data.get("phase")
        if phase == "COMPLETED":
            break
        elif phase == "ERROR":
            raise RuntimeError(f"Job failed: {job_data}")
        time.sleep(poll_interval)
    else:
        raise TimeoutError("Job did not complete in time")

    # 3. Get results
    results_url = job_data.get("results_url")
    if not results_url:
        raise RuntimeError("No results_url in job data")
    results_req = urllib.request.Request(
        results_url,
        headers={"Authorization": f"Token {token}"},
        method="GET",
    )
    with urllib.request.urlopen(results_req, timeout=20) as results_resp:
        results_data = json.loads(results_resp.read().decode("utf-8"))
    results = results_data.get("results", [])
    if not results:
        raise RuntimeError("No results found for job")
    result = results[0]
    download_url = result.get("download_url")
    if not download_url:
        raise RuntimeError("No download_url in result")

    # 4. Download result
    download_req = urllib.request.Request(
        download_url,
        headers={"Authorization": f"Token {token}"},
        method="GET",
    )
    with urllib.request.urlopen(download_req, timeout=60) as dl_resp:
        status = dl_resp.getcode()
        content_type = dl_resp.headers.get("Content-Type", "")
        body = dl_resp.read()
    return status, content_type, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Test /api/async endpoint")
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
        default="/tmp/async_result_test.fits",
        help="Output file path for successful binary response",
    )
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval in seconds")
    parser.add_argument("--max-polls", type=int, default=30, help="Maximum polling attempts")
    args = parser.parse_args()

    try:
        token = get_token(args.base_url, args.username, args.password)
        print("auth: ok")

        status, content_type, body = call_async_cutout(
            base_url=args.base_url,
            token=token,
            survey_id=args.survey_id,
            pos=args.pos,
            engine=args.engine,
            output_format=args.output_format,
            band=args.band,
            poll_interval=args.poll_interval,
            max_polls=args.max_polls,
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
