#!/usr/bin/env python3
"""
Dispatch a cutout job directly to Celery workers, bypassing the HTTP API.
Useful for testing worker execution in isolation.

Usage:
    docker compose exec django python test_worker_dispatch.py --job-id 103
    docker compose exec django python test_worker_dispatch.py --job-id 103 --reset
"""
from __future__ import annotations

import argparse
import os
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from cutout.service.models import Job as SQLJob  # noqa: E402
from cutout.service.uws.service import JobService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch a cutout job directly to Celery workers")
    parser.add_argument("--job-id", required=True, type=int, help="ID of the job to dispatch")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset job to PENDING before dispatching (required if job already ran)",
    )
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds")
    parser.add_argument("--max-polls", type=int, default=60, help="Maximum poll attempts before timeout")
    args = parser.parse_args()

    try:
        sqljob = SQLJob.objects.get(pk=args.job_id)
    except SQLJob.DoesNotExist:
        print(f"error: job {args.job_id} not found")
        return 1

    print(f"job found: id={sqljob.id}  phase={sqljob.phase}  owner={sqljob.owner}")
    params = list(sqljob.parameters.order_by("id").values_list("parameter", "value"))
    print(f"  params: {params}")

    terminal_phases = (
        SQLJob.ExecutionPhase.COMPLETED,
        SQLJob.ExecutionPhase.ERROR,
        SQLJob.ExecutionPhase.ABORTED,
        SQLJob.ExecutionPhase.EXECUTING,
        SQLJob.ExecutionPhase.QUEUED,
    )
    if sqljob.phase in terminal_phases:
        if not args.reset:
            print(f"  job is already in phase={sqljob.phase}. Use --reset to re-dispatch.")
            return 1
        sqljob.phase = SQLJob.ExecutionPhase.PENDING
        sqljob.message_id = None
        sqljob.start_time = None
        sqljob.end_time = None
        sqljob.results.all().delete()
        sqljob.save()
        print("  reset to PENDING")

    # Dispatch via the same service layer the API uses
    job_service = JobService()
    job_service.start_async(sqljob.owner, sqljob.id)
    print(f"  dispatched — polling every {args.poll_interval}s (max {args.max_polls} attempts)")

    # Poll until terminal state
    for i in range(1, args.max_polls + 1):
        time.sleep(args.poll_interval)
        sqljob.refresh_from_db()
        phase = sqljob.phase
        print(f"  [{i:2d}] phase={phase}")
        if phase == SQLJob.ExecutionPhase.COMPLETED:
            break
        elif phase in (SQLJob.ExecutionPhase.ERROR, SQLJob.ExecutionPhase.ABORTED):
            print("  job ended with failure")
            return 1
    else:
        print(f"  timeout: job did not complete after {args.max_polls} polls")
        return 1

    # Print results
    results = list(sqljob.results.order_by("sequence"))
    print(f"\nresults ({len(results)}):")
    for r in results:
        print(f"  [{r.sequence}] result_id : {r.result_id}")
        print(f"       file     : {r.file_path}")
        print(f"       mime     : {r.mime_type}")
        print(f"       size     : {r.size} bytes")
        print(f"       url      : {r.url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
