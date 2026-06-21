#!/usr/bin/env python3
"""Iteration 6 — Build + freeze the REAL 3D LV (CAMUS Simpson's biplane) demo.

Reconstructs one CAMUS patient's LV at ED and ES from the expert masks, computes
EDV/ESV/EF (clinical biplane formula), exports a BEATING glb (ED<->ES morph) plus a
static fallback, narrates honestly, validates EF against the CAMUS reference, and
freezes everything for the offline AR page.

  demo/golden_camus/      meta.json, beating.glb         (backend copy)
  frontend/golden_camus/  beating.glb, lv_ed.glb, meta.json   (AR page, offline)

Cite: Leclerc et al., IEEE TMI 2019 (doi:10.1109/TMI.2019.2900516) — REQUIRED.

    python scripts/build_camus_demo.py [patientXXXX]
"""

from __future__ import annotations

import json
import os
import shutil
import sys

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import render_preview as rp
from app import camus_biplane as cb, narration

DB = os.path.join(ROOT, "data", "database_nifti")
BACK = os.path.join(ROOT, "demo", "golden_camus")
FRONT = os.path.join(ROOT, "frontend", "golden_camus")
CITATION = ("CAMUS dataset — S. Leclerc et al., 'Deep Learning for Segmentation using "
            "an Open Large-Scale Dataset in 2D Echocardiography', IEEE TMI 38(9):2198-2210, "
            "2019. doi:10.1109/TMI.2019.2900516")
METHOD = ("3D LV reconstructed from CAMUS 2D apical views (2CH+4CH) via Simpson's "
          "biplane method of discs; EF by the clinical biplane formula. NOT a 3D-echo "
          "volume acquisition.")


def _render(rec_phase, out_png, title):
    m = trimesh.Trimesh(rec_phase["verts"], rec_phase["faces"], process=True)
    m.fix_normals()
    fn = m.face_normals
    rp.render_turntable(m, out_png, rp._shade(fn, rp.TISSUE), title)


def _static_glb(rec_phase, out_path):
    """A meters-scaled, recentered static LV glb (offline fallback if the animated
    glb can't load)."""
    v = (np.asarray(rec_phase["verts"]) - np.asarray(rec_phase["verts"]).mean(0)) * 0.01
    m = trimesh.Trimesh(v, rec_phase["faces"], process=True); m.fix_normals()
    m.export(out_path, file_type="glb")


def pick_patient(preferred: str | None):
    cands = ([preferred] if preferred else []) + [f"patient{n:04d}" for n in range(1, 12)]
    for pid in cands:
        pdir = os.path.join(DB, pid)
        if not os.path.isdir(pdir):
            continue
        try:
            r = cb.reconstruct_patient(pdir)
        except Exception as e:
            print(f"  {pid}: reconstruction failed ({e}); trying next.")
            continue
        edv, ef = r["EDV_mL"], r["EF_pct"]
        if 30 <= edv <= 250 and 10 <= ef <= 85 and r["ESV_mL"] > 0:
            return r, pdir
        print(f"  {pid}: degenerate (EDV={edv}, EF={ef}); trying next patient.")
    return None, None


def main() -> int:
    os.makedirs(BACK, exist_ok=True); os.makedirs(FRONT, exist_ok=True)
    preferred = sys.argv[1] if len(sys.argv) > 1 else "patient0001"

    r, pdir = pick_patient(preferred)
    if r is None:
        print("ERROR: no patient produced a plausible biplane LV.", file=sys.stderr)
        return 1
    pid = r["patient"]
    ed, es = r["ed"], r["es"]

    print(f"=== {pid} (image quality: {r['image_quality']}) ===")
    print(f"EDV = {r['EDV_mL']} mL   ESV = {r['ESV_mL']} mL   EF = {r['EF_pct']} %")
    ref = r["reference_ef"]
    if ref is not None:
        print(f"CAMUS reference EF = {ref} %   (ours - ref = {r['EF_pct']-ref:+.1f} pp)")
    print("EF physiological (40-70% normal):", 40 <= r["EF_pct"] <= 75)

    # Beating glb (ED<->ES morph) + static fallback
    beating_ok = cb.write_beating_glb(ed["verts"], es["verts"], ed["faces"],
                                      os.path.join(FRONT, "beating.glb"))
    if beating_ok:
        shutil.copyfile(os.path.join(FRONT, "beating.glb"), os.path.join(BACK, "beating.glb"))
        print("beating.glb written (ED<->ES morph animation).")
    else:
        print("pygltflib unavailable — beating.glb skipped; static ED/ES fallback only.")
    _static_glb(ed, os.path.join(FRONT, "lv_ed.glb"))
    _static_glb(es, os.path.join(FRONT, "lv_es.glb"))

    # Narration (honest)
    summary = {"anatomy_label": "the heart's left ventricle",
               "EDV_mL": r["EDV_mL"], "ESV_mL": r["ESV_mL"], "EF_pct": r["EF_pct"],
               "reference_ef": ref, "image_quality": r["image_quality"], "method": METHOD}
    narr = narration.narrate_camus(summary)

    meta = {
        "data_source": "REAL",
        "modality": "2D echocardiography (CAMUS) -> Simpson's biplane 3D LV",
        "patient": pid, "image_quality": r["image_quality"],
        "EDV_mL": r["EDV_mL"], "ESV_mL": r["ESV_mL"], "EF_pct": r["EF_pct"],
        "reference_ef": ref,
        "ef_vs_reference_pp": (round(r["EF_pct"] - ref, 1) if ref is not None else None),
        "n_discs": r["n_discs"], "spacing_mm": r["spacing_mm"],
        "beating": bool(beating_ok),
        "method": METHOD, "citation": CITATION,
        "is_synthetic_placeholder": False,
        "narration": narr["text"], "narration_mode": narr["mode"], "narration_model": narr["model"],
        "confidence_note": (f"Expert-annotated masks (CAMUS, image quality "
                            f"'{r['image_quality']}'). Biplane is a geometric estimate; "
                            "apical foreshortening and the elliptical-disc assumption are "
                            "its known limitations."),
    }
    for d in (FRONT, BACK):
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2)

    _render(ed, os.path.join(ROOT, "preview", "camus_lv_ed.png"),
            f"CAMUS {pid} LV (ED) — Simpson biplane | EDV={r['EDV_mL']:.0f} mL")
    _render(es, os.path.join(ROOT, "preview", "camus_lv_es.png"),
            f"CAMUS {pid} LV (ES) — Simpson biplane | ESV={r['ESV_mL']:.0f} mL")

    print(f"narration[{narr['mode']}]: {narr['text']}")
    print(f"frozen -> {FRONT}/ + {BACK}/  (beating.glb, lv_ed.glb, meta.json)")
    print("previews -> preview/camus_lv_ed.png, preview/camus_lv_es.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
