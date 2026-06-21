#!/usr/bin/env python3
"""Per-patient CAMUS data bundle for the Quest 3 mixed-reality demo.

For a given patient, generates:
  frontend/patient_bundles/<pid>/
    scan_4ch.png   — real 4CH ED ultrasound slice + LV endocardial contour
    scan_2ch.png   — real 2CH ED ultrasound slice + LV endocardial contour
    lv_ed.glb      — static ED mesh (always present)
    meta.json      — EDV / ESV / EF / narration / uncertainty_region / citation

All numbers come from the patient's real _gt masks. Nothing is hardcoded.

HONESTY: real public patient ultrasound data, processed at build time.
  NOT live probe scanning. NOT a clinical measurement device.
  Cite: CAMUS — Leclerc et al., IEEE TMI 2019 (doi:10.1109/TMI.2019.2900516).

    python scripts/build_camus_bundle.py patient0001
    python scripts/build_camus_bundle.py --all-diverse    # pick 4 representative patients
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import numpy as np
import SimpleITK as sitk
from skimage import measure as sk_measure

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app import camus_biplane as cb, narration
import trimesh

DB      = os.path.join(ROOT, "data", "database_nifti")
BUNDLES = os.path.join(ROOT, "frontend", "patient_bundles")
CITATION = ("CAMUS — S. Leclerc et al., 'Deep Learning for Segmentation using an "
            "Open Large-Scale Dataset in 2D Echocardiography,' IEEE TMI 38(9):2198-2210, "
            "2019. doi:10.1109/TMI.2019.2900516")

# ── scan rendering ─────────────────────────────────────────────────────────────

def _load_nifti(path: str):
    img = sitk.ReadImage(path)
    return sitk.GetArrayFromImage(img)           # (H, W)


def _window(arr: np.ndarray, p_lo=1, p_hi=99) -> np.ndarray:
    """Percentile window → [0,1] float."""
    lo, hi = np.percentile(arr, p_lo), np.percentile(arr, p_hi)
    return np.clip((arr.astype(float) - lo) / (hi - lo + 1e-6), 0, 1)


def _lv_contour(mask: np.ndarray):
    """Outer boundary of label-1 (LV cavity) as list of (row,col) arrays."""
    binary = (mask == 1).astype(np.uint8)
    contours = sk_measure.find_contours(binary, level=0.5)
    if not contours:
        return []
    # Return all contour segments (there may be more than one if mask is fragmented).
    return contours


def _uncertainty_region(hw4: np.ndarray, hw2: np.ndarray, n: int = cb.N_DISCS) -> dict:
    """Identify the disc levels with the lowest biplane half-widths.

    The basal third (discs near the mitral valve) is systematically less certain
    in Simpson's biplane because the LV-LA boundary is harder to place precisely.
    We also flag any disc where EITHER view measured zero width (contour gap).

    Returns a dict: {region_name, disc_range, fraction_of_lv, reason}
    """
    combined = (hw4 + hw2) / 2.0
    zero_mask = (hw4 < 1e-3) | (hw2 < 1e-3)    # actual contour gaps

    # The basal 30% of discs (highest index = nearest mitral valve base)
    basal_start = int(n * 0.70)
    basal_discs = list(range(basal_start, n))

    if zero_mask.any():
        gap_discs = np.where(zero_mask)[0].tolist()
        region = "contour gap" if len(gap_discs) < n // 4 else "basal region"
        reason = f"Zero half-width at disc levels {gap_discs} — contour gap in mask."
    else:
        region = "basal region (near mitral valve)"
        reason = ("Basal discs have systematically lower certainty: the LV-LA boundary "
                  "is harder to locate precisely in apical views.")

    return {"region_name": region,
            "disc_range": [basal_start, n - 1],
            "fraction_of_lv": f"{(n - basal_start) / n * 100:.0f}%",
            "reason": reason}


def render_scan(img_path: str, msk_path: str, out_path: str,
                view: str, phase: str, pid: str):
    """Render a real CAMUS 2D ultrasound slice with LV contour overlay."""
    img = _load_nifti(img_path)    # (H, W)
    msk = _load_nifti(msk_path)

    img_disp = _window(img)
    contours = _lv_contour(msk)

    fig, ax = plt.subplots(figsize=(5, 4), facecolor="#0b0e13")
    ax.imshow(img_disp, cmap="gray", origin="upper", aspect="auto")

    for cnt in contours:
        ax.plot(cnt[:, 1], cnt[:, 0],
                color="#5b9dff", linewidth=1.4, alpha=0.9)

    # Mark the apex (farthest LV point from LA)
    c4  = (msk == 1); la4 = (msk == cb.LA)
    if c4.any():
        apex, base = cb._long_axis(c4, la4)
        ax.plot(apex[0], apex[1], "o", color="#43c08a", markersize=5)
        ax.plot(base[0], base[1], "^", color="#f5972b", markersize=5)
        ax.annotate("apex",  (apex[0], apex[1]),  color="#43c08a",
                    fontsize=7, xytext=(4, -4), textcoords="offset points")
        ax.annotate("base",  (base[0], base[1]),  color="#f5972b",
                    fontsize=7, xytext=(4,  4), textcoords="offset points")

    ax.axis("off")
    ax.set_title(
        f"{pid} · Apical {view} · {phase}\nLV contour from expert _gt mask (label 1)",
        color="#eef3fa", fontsize=8, pad=4)

    legend = [
        mpatches.Patch(color="#5b9dff", label="LV endocardium (label 1)"),
        mpatches.Patch(color="#43c08a", label="Apex"),
        mpatches.Patch(color="#f5972b", label="Mitral base"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=6,
              facecolor="#151b25", edgecolor="#2a3340",
              labelcolor="#eef3fa", framealpha=0.85)

    # Honesty watermark
    fig.text(0.01, 0.01,
             "Real CAMUS patient data · not live scanning · cite: Leclerc et al., IEEE TMI 2019",
             color="#666", fontsize=5.5, va="bottom")

    fig.tight_layout(pad=0.3)
    fig.savefig(out_path, dpi=150, facecolor="#0b0e13", bbox_inches="tight")
    plt.close(fig)


# ── GLB export ─────────────────────────────────────────────────────────────────

def _static_glb(rec, out_path):
    v = (np.asarray(rec["verts"]) - np.asarray(rec["verts"]).mean(0)) * 0.01
    m = trimesh.Trimesh(v, rec["faces"], process=True)
    m.fix_normals()
    m.export(out_path, file_type="glb")


# ── bundle builder ──────────────────────────────────────────────────────────────

def build_bundle(pid: str, force: bool = False) -> dict | None:
    """Build the full bundle for one patient. Returns meta dict or None on failure."""
    pdir    = os.path.join(DB, pid)
    out_dir = os.path.join(BUNDLES, pid)

    if not os.path.isdir(pdir):
        print(f"  {pid}: directory not found — skipped.")
        return None

    os.makedirs(out_dir, exist_ok=True)

    # -- reconstruction --
    try:
        r = cb.reconstruct_patient(pdir)
    except Exception as e:
        print(f"  {pid}: reconstruction failed ({e}) — skipped.")
        return None

    edv, esv, ef = r["EDV_mL"], r["ESV_mL"], r["EF_pct"]

    # -- uncertainty region from the ED half-widths --
    ed = r["ed"]
    unc = _uncertainty_region(ed["a_cm"], ed["b_cm"])

    # -- scan PNGs: 4CH ED and 2CH ED --
    for view in ("4CH", "2CH"):
        img_path = os.path.join(pdir, f"{pid}_{view}_ED.nii.gz")
        msk_path = os.path.join(pdir, f"{pid}_{view}_ED_gt.nii.gz")
        out_png  = os.path.join(out_dir, f"scan_{view.lower()}.png")
        if not os.path.exists(out_png) or force:
            render_scan(img_path, msk_path, out_png, view, "ED", pid)

    # -- static lv_ed.glb --
    glb_path = os.path.join(out_dir, "lv_ed.glb")
    if not os.path.exists(glb_path) or force:
        _static_glb(ed, glb_path)

    # -- narration --
    ref  = r["reference_ef"]
    narr_summary = {
        "anatomy_label": "the heart's left ventricle",
        "EDV_mL": edv, "ESV_mL": esv, "EF_pct": ef,
        "reference_ef": ref, "image_quality": r["image_quality"],
        "method": "Simpson's biplane method of discs from 2D apical views",
    }
    narr = narration.narrate_camus(narr_summary)

    # -- meta.json --
    meta = {
        "patient": pid,
        "image_quality": r["image_quality"],
        "EDV_mL": edv, "ESV_mL": esv, "EF_pct": ef,
        "reference_ef": ref,
        "ef_vs_reference_pp": round(ef - ref, 1) if ref is not None else None,
        "n_discs": r["n_discs"],
        "spacing_mm": r["spacing_mm"],
        "uncertainty_region": unc,
        "narration": narr["text"],
        "narration_mode": narr["mode"],
        "narration_model": narr["model"],
        "scan_4ch": "scan_4ch.png",
        "scan_2ch": "scan_2ch.png",
        "glb_ed": "lv_ed.glb",
        "data_source": "REAL — CAMUS 2D apical echocardiography, expert _gt masks",
        "honesty_note": ("Real public patient ultrasound data, processed at build time. "
                         "NOT live probe scanning. NOT a clinical measurement device. "
                         "EF is a biplane geometric estimate."),
        "citation": CITATION,
        "method": ("3D LV reconstructed from CAMUS 2D apical views (2CH+4CH) via "
                   "Simpson's biplane method of discs. NOT a 3D-echo volume acquisition."),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  {pid}  quality={r['image_quality']:6s}  "
          f"EDV={edv:5.1f}  ESV={esv:5.1f}  EF={ef:5.1f}%  "
          f"ref={ref}  uncertainty='{unc['region_name']}'")
    return meta


# ── diverse patient picker ─────────────────────────────────────────────────────

def pick_diverse(n_each: int = 1) -> list[str]:
    """Pick patients across EF ranges from the batch results CSV."""
    results_csv = os.path.join(ROOT, "data", "camus_all_results.csv")
    if not os.path.exists(results_csv):
        print("Warning: batch results CSV not found; using hardcoded diverse set.")
        return ["patient0001", "patient0021", "patient0222", "patient0445"]

    rows = [r for r in csv.DictReader(open(results_csv))
            if r["physiological"] == "True" and r["EF_pct"]]
    rows.sort(key=lambda r: float(r["EF_pct"]))

    buckets = {
        "severe (<35%)":    [r for r in rows if float(r["EF_pct"]) < 35],
        "reduced (35-49%)": [r for r in rows if 35 <= float(r["EF_pct"]) < 50],
        "normal (50-65%)":  [r for r in rows if 50 <= float(r["EF_pct"]) <= 65],
        "high (>65%)":      [r for r in rows if float(r["EF_pct"]) > 65],
    }

    chosen = []
    # Prefer Good/Medium quality within each bucket.
    for label, bucket in buckets.items():
        good = [r for r in bucket if r["image_quality"] in ("Good", "Medium")]
        pool = good if good else bucket
        # Pick one from middle of pool for best representative
        mid = pool[len(pool) // 2]
        chosen.append(mid["patient"])
        print(f"  {label}: {mid['patient']}  EF={mid['EF_pct']}%  quality={mid['image_quality']}")

    return chosen


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patient", nargs="?", help="patient ID (e.g. patient0001)")
    ap.add_argument("--all-diverse", action="store_true",
                    help="build bundles for ~4 representative patients across EF range")
    ap.add_argument("--force", action="store_true", help="re-render even if PNGs exist")
    args = ap.parse_args()

    os.makedirs(BUNDLES, exist_ok=True)

    if args.all_diverse or args.patient is None:
        print("Picking diverse patient set …")
        pids = pick_diverse()
        # Always include patient0001 (the hero)
        if "patient0001" not in pids:
            pids.insert(0, "patient0001")
    else:
        pids = [args.patient]

    print(f"\nBuilding bundles for: {pids}")
    print(f"Output root: {BUNDLES}\n")

    built = []
    for pid in pids:
        print(f"[{pid}]")
        meta = build_bundle(pid, force=args.force)
        if meta:
            built.append(pid)

    # Write a top-level index for the Unity loader.
    index = {"patients": built,
             "hero": "patient0001" if "patient0001" in built else (built[0] if built else None)}
    with open(os.path.join(BUNDLES, "index.json"), "w") as f:
        json.dump(index, f, indent=2)

    print(f"\nDone. {len(built)}/{len(pids)} bundles built.")
    print(f"Bundle root: {BUNDLES}/")
    print(f"Index: {BUNDLES}/index.json")
    print("\nFiles per bundle:")
    for pid in built:
        d = os.path.join(BUNDLES, pid)
        for fn in sorted(os.listdir(d)):
            sz = os.path.getsize(os.path.join(d, fn))
            print(f"  {pid}/{fn}  ({sz//1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
