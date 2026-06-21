#!/usr/bin/env python3
"""Iteration 6 / step 1 — VERIFY the CAMUS data before coding (do not assume).

CAMUS = 2D echocardiography (apical 2-chamber + 4-chamber views), with expert
segmentation masks. This script loads a few patients and prints, per file:
shape, ndim, spacing, image-vs-_gt, and the view/phase parsed from the filename
(e.g. patient0001_4CH_ED.nii.gz). For masks it prints the label histogram
(expected 0=bg, 1=LV cavity/endocardium, 2=myocardium, 3=left atrium). It also
finds patients that have all four of {2CH,4CH}×{ED,ES} as image+gt (needed for
Simpson's biplane).

We do NOT stack 2D frames into a fake depth axis. The honest 3D comes later from
the expert contours via Simpson's biplane method of discs.

    python scripts/inspect_camus.py
"""

from __future__ import annotations

import glob
import os
import re

import numpy as np
import SimpleITK as sitk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB = os.path.join(ROOT, "data", "database_nifti")

NAME_RE = re.compile(r"patient(\d+)_(2CH|4CH)_(ED|ES)(_gt)?\.nii\.gz$")
NEEDED = [("2CH", "ED"), ("2CH", "ES"), ("4CH", "ED"), ("4CH", "ES")]


def load(path):
    img = sitk.ReadImage(path)
    arr = sitk.GetArrayFromImage(img)        # (z?,H,W) or (H,W)
    return img, arr


def parse(fn):
    m = NAME_RE.search(fn)
    if not m:
        return None
    return {"patient": int(m.group(1)), "view": m.group(2),
            "phase": m.group(3), "is_gt": bool(m.group(4))}


def inspect_patient(pdir, verbose=True):
    files = sorted(glob.glob(os.path.join(pdir, "*_E[DS]*.nii.gz")))
    have = set()
    info = []
    for f in files:
        meta = parse(os.path.basename(f))
        if not meta:
            continue
        img, arr = load(f)
        sp = img.GetSpacing()
        rec = {**meta, "shape": tuple(arr.shape), "ndim": arr.ndim,
               "spacing_mm": tuple(round(s, 4) for s in sp)}
        if meta["is_gt"]:
            vals, cnts = np.unique(arr, return_counts=True)
            rec["labels"] = {int(v): int(c) for v, c in zip(vals, cnts)}
        else:
            have.add((meta["view"], meta["phase"]))
        info.append(rec)
        if verbose:
            tag = "_gt MASK" if meta["is_gt"] else "image  "
            extra = f"labels={rec.get('labels')}" if meta["is_gt"] else ""
            print(f"  {meta['view']}_{meta['phase']} {tag} shape={rec['shape']} "
                  f"ndim={rec['ndim']} spacing(mm)={rec['spacing_mm']} {extra}")
    complete = all(vp in have for vp in NEEDED)
    return complete, info


def main():
    patients = sorted(glob.glob(os.path.join(DB, "patient*")))
    print(f"CAMUS root: {DB}")
    print(f"patients found: {len(patients)}")
    if not patients:
        print("ERROR: no patients found — is the data unpacked at data/database_nifti/?")
        return 1

    # Detailed look at the first few.
    for pdir in patients[:3]:
        print(f"\n=== {os.path.basename(pdir)} ===")
        complete, _ = inspect_patient(pdir)
        print(f"  has all 4 (2CH/4CH x ED/ES image+gt)? {complete}")

    # Find the first N patients that are complete (candidates for the biplane recon).
    print("\n=== scanning for complete patients (all 4 views/phases + masks) ===")
    complete_list = []
    for pdir in patients:
        files = {os.path.basename(f) for f in glob.glob(os.path.join(pdir, "*.nii.gz"))}
        pid = os.path.basename(pdir)
        ok = all(f"{pid}_{v}_{ph}.nii.gz" in files and f"{pid}_{v}_{ph}_gt.nii.gz" in files
                 for v, ph in NEEDED)
        if ok:
            complete_list.append(pid)
    print(f"complete patients: {len(complete_list)} / {len(patients)}")
    print("first 8 complete:", complete_list[:8])
    print("\nDONE. CAMUS is 2D apical echo (per shapes above). Use the _gt LV-cavity "
          "label (1) contours for the Simpson's biplane reconstruction — no fake depth.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
