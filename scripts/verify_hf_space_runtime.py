#!/usr/bin/env python3
"""Post-deploy HF Space runtime verification gate.

After ``upload_folder`` succeeds, the deploy script currently treats that
as a green deploy. But HF Space does the actual Docker build / Gradio
launch ASYNCHRONOUSLY -- and that pass can still fail in ways the upload
step never sees:

  - BUILD_ERROR    -- pip install failed (e.g. gradio version drift, a
                      yanked package, a system-library mismatch)
  - CONFIG_ERROR   -- README frontmatter rejected
  - RUNTIME_ERROR  -- the build produced a Docker image but app.py crashes
                      at startup (model load fail / NLTK download fail /
                      gradio API breakage)
  - NO_APP_FILE    -- bundle missing the file pointed to by `app_file:`

The 2026-06 incident (PR #583) was exactly this class of failure: the
deploy workflow reported "Successfully deployed", but the Space was stuck
in BUILD_ERROR for weeks before anyone noticed by manually opening the
demo URL.

This script closes the loop: poll ``HfApi.get_space_runtime`` after deploy
and fail the workflow if the Space does not reach a healthy stage within
a budget.

Healthy stages (success): RUNNING, RUNNING_BUILDING, APP_STARTING
                          (APP_STARTING / RUNNING_BUILDING are transient on
                          the way to RUNNING and acceptable as final states
                          if poll budget runs out -- the Space IS serving
                          requests in those stages.)
In-progress stages (continue polling): BUILDING
Failure stages (exit immediately): BUILD_ERROR, RUNTIME_ERROR, CONFIG_ERROR,
                                    NO_APP_FILE, PAUSED, STOPPED, DELETING

Usage:
    HF_TOKEN=... python scripts/verify_hf_space_runtime.py \\
        --space-id ayousanz/piper-plus-demo \\
        --timeout-seconds 600 \\
        --poll-interval-seconds 20

Exit codes:
    0 -- Space reached a healthy stage within the budget
    1 -- Space entered a failure stage, OR poll budget exhausted while
         still BUILDING (the build is unusually slow -- worth investigating
         manually even if it eventually succeeds)
    2 -- usage / auth error (could not query the API at all)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

HEALTHY_STAGES = frozenset({"RUNNING", "RUNNING_BUILDING", "APP_STARTING"})
IN_PROGRESS_STAGES = frozenset({"BUILDING"})
# Anything else (BUILD_ERROR, RUNTIME_ERROR, CONFIG_ERROR, NO_APP_FILE,
# PAUSED, STOPPED, DELETING) we treat as failure. We list the recognized
# failure stages explicitly for the diagnostic message; unknown stages also
# fail closed (safer than treating an unknown stage as healthy).
KNOWN_FAILURE_STAGES = frozenset(
    {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE", "PAUSED", "STOPPED", "DELETING"}
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--space-id",
        required=True,
        help="HF Space repo id (e.g. ayousanz/piper-plus-demo)",
    )
    p.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="Maximum total wall-clock time to wait for a healthy stage. "
        "Default 600 (10 min). Our normal build is 5-8 min; 10 min gives "
        "headroom for HF queue contention without letting a truly broken "
        "deploy hang the workflow.",
    )
    p.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=20,
        help="Seconds between HF API polls. Default 20. Lower wastes API "
        "budget; higher delays failure detection.",
    )
    p.add_argument(
        "--allow-startup-grace-seconds",
        type=int,
        default=30,
        help="Wait this long after upload before the FIRST poll. HF sometimes "
        "takes a few seconds to register the upload and transition out of "
        "the previous stage; polling immediately can return a stale RUNNING "
        "stage from the prior deploy.",
    )
    return p.parse_args()


def _get_stage(api, space_id: str) -> tuple[str, object]:
    """Return (stage_string, raw_runtime_object).

    Returns (\"\", None) if the API call fails -- caller decides whether to
    retry or give up.
    """
    try:
        runtime = api.get_space_runtime(space_id)
    except Exception as e:  # noqa: BLE001 -- any API failure is "try again"
        print(f"  (warning) get_space_runtime failed: {e}", flush=True)
        return "", None
    stage = getattr(runtime, "stage", "") or ""
    return str(stage), runtime


def main() -> int:
    args = _parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        print(
            "ERROR: HF_TOKEN env var is required (set it to a token with "
            "read access to the Space)",
            file=sys.stderr,
        )
        return 2

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print(
            "ERROR: huggingface_hub is not installed (`pip install -U "
            "huggingface_hub`)",
            file=sys.stderr,
        )
        return 2

    api = HfApi(token=token)

    print(
        f"Verifying HF Space '{args.space_id}' reaches a healthy stage "
        f"within {args.timeout_seconds}s "
        f"(poll every {args.poll_interval_seconds}s)..."
    )

    if args.allow_startup_grace_seconds > 0:
        print(
            f"  Waiting {args.allow_startup_grace_seconds}s for HF to register "
            "the upload..."
        )
        time.sleep(args.allow_startup_grace_seconds)

    deadline = time.monotonic() + args.timeout_seconds
    last_stage = ""
    poll_count = 0

    while True:
        poll_count += 1
        stage, _runtime = _get_stage(api, args.space_id)
        elapsed = int(args.timeout_seconds - max(0, deadline - time.monotonic()))

        if stage:
            if stage != last_stage:
                print(f"  [{elapsed:>4}s, poll #{poll_count}] stage={stage}")
                last_stage = stage
            else:
                print(f"  [{elapsed:>4}s, poll #{poll_count}] (still {stage})")
        else:
            print(f"  [{elapsed:>4}s, poll #{poll_count}] (transient API error)")

        if stage in HEALTHY_STAGES:
            print(
                f"\nOK: HF Space reached healthy stage '{stage}' "
                f"after {elapsed}s ({poll_count} polls)"
            )
            print(f"     Space URL: https://huggingface.co/spaces/{args.space_id}")
            return 0

        if stage in KNOWN_FAILURE_STAGES:
            print(
                f"\nFAIL: HF Space entered failure stage '{stage}' "
                f"after {elapsed}s"
            )
            print(
                "      Inspect the build / runtime log at "
                f"https://huggingface.co/spaces/{args.space_id}?logs=build "
                "(swap to ?logs=container for runtime errors)."
            )
            return 1

        if stage and stage not in IN_PROGRESS_STAGES:
            # Unknown stage -- log it but keep polling for a couple more
            # cycles in case HF added a new transitional stage. Treat as
            # failure if we reach the deadline still in this stage.
            print(
                f"      (warning: unrecognized stage '{stage}', "
                "treating as in-progress for now)"
            )

        if time.monotonic() >= deadline:
            print(
                f"\nFAIL: timed out after {args.timeout_seconds}s with "
                f"final stage='{stage or 'unknown'}'. A healthy build "
                "completes in 5-8 minutes; this is unusually slow and "
                "likely stuck. Check the Space build log."
            )
            return 1

        time.sleep(args.poll_interval_seconds)


if __name__ == "__main__":
    sys.exit(main())
