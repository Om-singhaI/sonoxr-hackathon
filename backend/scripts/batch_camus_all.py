#!/usr/bin/env python3
"""Run Simpson's biplane reconstruction on ALL 500 CAMUS patients.

Outputs:
  data/camus_all_results.csv   — one row per patient
  data/camus_all_summary.json  — aggregate stats

    python scripts/batch_camus_all.py
"""

from __future__ import annotations

import csv
import glob
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app import camus_biplane as cb

DB   = os.path.join(ROOT, "data", "database_nifti")
OUT_CSV  = os.path.join(ROOT, "data", "camus_all_results.csv")
OUT_JSON = os.path.join(ROOT, "data", "camus_all_summary.json")

FIELDS = ["patient", "image_quality", "EDV_mL", "ESV_mL", "EF_pct",
          "reference_ef", "ef_error_pp", "physiological", "error"]

PHYS_BOUNDS = dict(edv_lo=30, edv_hi=250, esv_lo=5, ef_lo=10, ef_hi=85)


def is_physiological(r):
    b = PHYS_BOUNDS
    return (b["edv_lo"] <= r["EDV_mL"] <= b["edv_hi"] and
            r["ESV_mL"] >= b["esv_lo"] and
            b["ef_lo"] <= r["EF_pct"] <= b["ef_hi"])


def main():
    patients = sorted(glob.glob(os.path.join(DB, "patient*")))
    n = len(patients)
    print(f"CAMUS batch: {n} patients found at {DB}")
    if n == 0:
        print("ERROR: no patients found.")
        return 1

    rows = []
    t0 = time.time()
    ok_count = fail_count = degen_count = 0

    with open(OUT_CSV, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()

        for i, pdir in enumerate(patients, 1):
            pid = os.path.basename(pdir)
            row = {"patient": pid, "image_quality": "", "EDV_mL": "",
                   "ESV_mL": "", "EF_pct": "", "reference_ef": "",
                   "ef_error_pp": "", "physiological": "", "error": ""}
            try:
                r = cb.reconstruct_patient(pdir)
                phys = is_physiological(r)
                ref  = r["reference_ef"]
                err  = round(r["EF_pct"] - ref, 1) if ref is not None else ""
                row.update(image_quality=r["image_quality"] or "",
                           EDV_mL=r["EDV_mL"], ESV_mL=r["ESV_mL"],
                           EF_pct=r["EF_pct"], reference_ef=ref or "",
                           ef_error_pp=err, physiological=phys)
                if phys:
                    ok_count += 1
                else:
                    degen_count += 1
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
                fail_count += 1

            writer.writerow(row)
            rows.append(row)

            # progress every 50 patients
            if i % 50 == 0 or i == n:
                elapsed = time.time() - t0
                rate = i / elapsed
                eta  = (n - i) / rate if rate > 0 else 0
                print(f"  [{i:3d}/{n}]  ok={ok_count}  degen={degen_count}"
                      f"  fail={fail_count}  elapsed={elapsed:.0f}s  eta={eta:.0f}s")
            elif i % 10 == 0:
                print(f"  [{i:3d}/{n}] ...", end="\r", flush=True)

    # ---------- aggregate stats ----------------------------------------
    good = [r for r in rows if r["physiological"] is True]
    ef_errors = [r["ef_error_pp"] for r in good
                 if isinstance(r["ef_error_pp"], (int, float))]
    efs       = [r["EF_pct"]      for r in good if isinstance(r["EF_pct"], (int, float))]
    edvs      = [r["EDV_mL"]      for r in good if isinstance(r["EDV_mL"], (int, float))]
    esvs      = [r["ESV_mL"]      for r in good if isinstance(r["ESV_mL"], (int, float))]

    def _stats(vals):
        if not vals: return {}
        import statistics
        return {"n": len(vals), "mean": round(statistics.mean(vals), 1),
                "stdev": round(statistics.stdev(vals), 1) if len(vals) > 1 else 0,
                "min": round(min(vals), 1), "max": round(max(vals), 1),
                "median": round(statistics.median(vals), 1)}

    summary = {
        "total_patients": n,
        "physiological": ok_count,
        "degenerate":    degen_count,
        "failed":        fail_count,
        "EF_pct":        _stats(efs),
        "EDV_mL":        _stats(edvs),
        "ESV_mL":        _stats(esvs),
        "ef_error_vs_reference_pp": _stats(ef_errors),
        "elapsed_s":     round(time.time() - t0, 1),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== BATCH COMPLETE ===")
    print(f"Total: {n}  |  physiological: {ok_count}  |  degenerate: {degen_count}"
          f"  |  failed: {fail_count}")
    print(f"EF  — mean {summary['EF_pct'].get('mean')}%  "
          f"stdev {summary['EF_pct'].get('stdev')}%  "
          f"range [{summary['EF_pct'].get('min')}–{summary['EF_pct'].get('max')}%]")
    print(f"EDV — mean {summary['EDV_mL'].get('mean')} mL  "
          f"range [{summary['EDV_mL'].get('min')}–{summary['EDV_mL'].get('max')} mL]")
    print(f"ESV — mean {summary['ESV_mL'].get('mean')} mL  "
          f"range [{summary['ESV_mL'].get('min')}–{summary['ESV_mL'].get('max')} mL]")
    if ef_errors:
        print(f"EF error vs CAMUS reference — mean {summary['ef_error_vs_reference_pp'].get('mean'):+.1f} pp  "
              f"stdev {summary['ef_error_vs_reference_pp'].get('stdev'):.1f} pp")
    print(f"Results -> {OUT_CSV}")
    print(f"Summary -> {OUT_JSON}")
    print(f"Elapsed: {summary['elapsed_s']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
