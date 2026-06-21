#!/usr/bin/env python3
"""TASK 1 — Lock + freeze the golden demo artifact.

Runs the demo pipeline ONCE on the locked demo subject (whatever /demo would
serve: a real volume in data/sample/real/ if present, else the curated synthetic
placeholder), times it, and FREEZES the produced artifacts into the repo so the
demo can run even if compute/network fails at the venue:

  demo/golden/            model.glb, narration.json, status.json  (backend L2 cache)
  frontend/golden/        model.glb, golden_meta.json             (AR-page L3, offline)

Re-run this whenever the demo subject changes (e.g. after dropping a real echo
volume into data/sample/real/).

    python scripts/freeze_golden.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app import pipeline

GOLDEN_DIR = os.path.join(ROOT, "demo", "golden")
FRONTEND_GOLDEN = os.path.join(ROOT, "frontend", "golden")
DEMO_TARGET_SECONDS = 10.0


def main() -> int:
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    os.makedirs(FRONTEND_GOLDEN, exist_ok=True)

    print("Running the demo pipeline to freeze the golden artifact…")
    t0 = time.time()
    job_id = pipeline.prepare_demo_job()
    status = pipeline.run_pipeline(job_id)
    elapsed = time.time() - t0

    if status["status"] != "done":
        print(f"ERROR: demo pipeline did not complete: {status.get('error')}",
              file=sys.stderr)
        return 1

    glb = pipeline.model_path(job_id)
    narr_path = pipeline.narration_path(job_id)
    narr = json.load(open(narr_path))

    # --- Freeze for the backend L2 cache ------------------------------------
    shutil.copyfile(glb, os.path.join(GOLDEN_DIR, "model.glb"))
    shutil.copyfile(narr_path, os.path.join(GOLDEN_DIR, "narration.json"))
    frozen_status = dict(status)
    frozen_status["frozen_golden"] = True
    frozen_status["frozen_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(os.path.join(GOLDEN_DIR, "status.json"), "w") as f:
        json.dump(frozen_status, f, indent=2)

    # --- Freeze for the AR-page L3 (fully offline, no backend) ---------------
    shutil.copyfile(glb, os.path.join(FRONTEND_GOLDEN, "model.glb"))
    summary = narr.get("summary", {})
    meta = {
        "narration": narr.get("narration"),
        "narration_mode": narr.get("mode"),
        "data_source": status.get("data_source"),
        "modality": status.get("modality"),
        "is_synthetic_placeholder": status.get("is_synthetic_placeholder"),
        "anatomy_label": status.get("anatomy_label"),
        "confidence": summary.get("confidence"),
        "approx_size": summary.get("approx_size"),
        "frozen_at": frozen_status["frozen_at"],
        "note": "Frozen golden artifact — offline fallback (L3) for the AR page.",
    }
    with open(os.path.join(FRONTEND_GOLDEN, "golden_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    # --- Report --------------------------------------------------------------
    glb_kb = os.path.getsize(glb) / 1024
    ok = "OK" if elapsed <= DEMO_TARGET_SECONDS else "SLOW"
    print(f"\n[{ok}] demo pipeline latency: {elapsed:.2f}s "
          f"(target <= {DEMO_TARGET_SECONDS:.0f}s, CPU)")
    print(f"demo subject : {status.get('data_source')} / {status.get('anatomy_label')}")
    print(f"modality     : {status.get('modality')}")
    print(f"glb          : {glb_kb:.0f} KB")
    print(f"confidence   : overall={summary.get('confidence',{}).get('overall')} "
          f"low={summary.get('confidence',{}).get('low_confidence_regions')}")
    print(f"narration[{narr.get('mode')}]: {narr.get('narration')}")
    print(f"\nFrozen -> {GOLDEN_DIR}/ (model.glb, narration.json, status.json)")
    print(f"Frozen -> {FRONTEND_GOLDEN}/ (model.glb, golden_meta.json)")
    if elapsed > DEMO_TARGET_SECONDS:
        print("\nNOTE: live recompute exceeds the target — /demo will lean on the "
              "frozen cache (L2) and the AR page loads the frozen artifact instantly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
