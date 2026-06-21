#!/usr/bin/env python3
"""Iteration 7 / Step 1 — Inspect the MSD dataset before any decision.

Finds the MSD task folder under data/, reads dataset.json (name, modality, labels,
numTraining), loads one imagesTr and one labelsTr file, and prints shape, ndim,
voxel spacing, and mask label values.

Reports:
  - Which MSD task this is
  - Modality (MRI / CT)
  - Whether it is a true 3D volume (ndim >= 3)
  - Decision recommendation per the Step-2 gate

DO NOT process further until this is reported.

    python scripts/inspect_msd.py
"""

from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import SimpleITK as sitk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

# MSD task folder names
MSD_TASK_NAMES = [
    "Task01_BrainTumour", "Task02_Heart", "Task03_Liver",
    "Task04_Hippocampus", "Task05_Prostate", "Task06_Lung",
    "Task07_Pancreas", "Task08_HepaticVessel", "Task09_Spleen",
    "Task10_Colon",
]
CARDIAC_TASKS = {"Task02_Heart"}


def find_task_dir() -> str | None:
    """Return the first MSD task directory containing dataset.json, searched recursively.

    Handles arbitrary nesting (e.g. data/Task02_Heart/Task02_Heart/dataset.json).
    """
    # Walk the whole data tree looking for dataset.json
    for dirpath, dirnames, filenames in os.walk(DATA):
        if "dataset.json" in filenames and "imagesTr" in dirnames:
            return dirpath
    # Fallback: any folder named Task0N_* regardless of contents
    for dirpath, dirnames, filenames in os.walk(DATA):
        base = os.path.basename(dirpath)
        if base.startswith("Task") and len(base) > 5:
            return dirpath
    return None


def load_one(folder: str) -> tuple[np.ndarray, tuple, str]:
    """Load the first NIfTI in folder; return (array, spacing_zyx, path)."""
    files = sorted(glob.glob(os.path.join(folder, "*.nii.gz")))
    if not files:
        raise FileNotFoundError(f"No .nii.gz found in {folder}")
    path = files[0]
    img = sitk.ReadImage(path)
    arr = sitk.GetArrayFromImage(img)          # shape: (Z, Y, X) or (Z, Y, X, T)
    sp = img.GetSpacing()                      # (X, Y, Z) in SimpleITK
    spacing_zyx = (sp[2], sp[1], sp[0])
    return arr, spacing_zyx, path


def main() -> int:
    print(f"Data root: {DATA}")
    print()

    task_dir = find_task_dir()
    if task_dir is None:
        print("ERROR: No MSD task folder found in data/.")
        print()
        print("Expected one of:")
        for name in MSD_TASK_NAMES:
            print(f"  data/{name}/")
        print()
        print("The MSD dataset does not appear to have been downloaded yet.")
        print("Download any task from: https://medicaldecathlon.com/")
        print("  (each task is a separate .tar archive; extract into data/)")
        print()
        print("Example (Task02_Heart, ~1.5 GB):")
        print("  wget https://drive.google.com/... -O Task02_Heart.tar")
        print("  tar -xf Task02_Heart.tar -C data/")
        return 2   # exit code 2 = dataset not present

    task_name = os.path.basename(task_dir)
    print(f"Found task: {task_name}  ({task_dir})")
    print()

    # --- dataset.json ---
    dsj = os.path.join(task_dir, "dataset.json")
    meta = {}
    if os.path.exists(dsj):
        meta = json.load(open(dsj))
        print("=== dataset.json ===")
        print(f"  name        : {meta.get('name')}")
        print(f"  modality    : {meta.get('modality')}")
        print(f"  labels      : {meta.get('labels')}")
        print(f"  numTraining : {meta.get('numTraining')}")
        print(f"  numTest     : {meta.get('numTest')}")
    else:
        print("(no dataset.json found — inferring from folder name)")

    modality_map = meta.get("modality", {})
    modality_str = " / ".join(modality_map.values()) if modality_map else "unknown"
    print()

    # --- load one image ---
    images_dir = os.path.join(task_dir, "imagesTr")
    labels_dir = os.path.join(task_dir, "labelsTr")

    if not os.path.isdir(images_dir):
        print(f"ERROR: imagesTr/ not found at {images_dir}")
        return 1

    print("=== sample image (imagesTr) ===")
    img_arr, img_sp, img_path = load_one(images_dir)
    print(f"  file      : {os.path.basename(img_path)}")
    print(f"  shape     : {img_arr.shape}  (Z, Y, X or Z, Y, X, channels)")
    print(f"  ndim      : {img_arr.ndim}")
    print(f"  dtype     : {img_arr.dtype}")
    print(f"  spacing   : z={img_sp[0]:.3f} mm  y={img_sp[1]:.3f} mm  x={img_sp[2]:.3f} mm")
    print(f"  value range: [{img_arr.min()}, {img_arr.max()}]")
    is_3d = img_arr.ndim >= 3 and img_arr.shape[0] > 1
    print(f"  true 3D volume? {is_3d}  (slices along Z = {img_arr.shape[0]})")
    print()

    if os.path.isdir(labels_dir):
        print("=== sample mask (labelsTr) ===")
        lbl_arr, lbl_sp, lbl_path = load_one(labels_dir)
        vals, counts = np.unique(lbl_arr, return_counts=True)
        print(f"  file      : {os.path.basename(lbl_path)}")
        print(f"  shape     : {lbl_arr.shape}")
        print(f"  ndim      : {lbl_arr.ndim}")
        print(f"  labels    : { {int(v): int(c) for v, c in zip(vals, counts)} }")
        # map label ids to names from dataset.json
        label_names = meta.get("labels", {})
        if label_names:
            print("  label names:", {int(v): label_names.get(str(int(v)), "?") for v in vals})
        print()

    # --- decision gate ---
    is_cardiac = task_name in CARDIAC_TASKS
    print("=" * 60)
    print("DECISION GATE (Step 2)")
    print("=" * 60)
    print(f"  Task          : {task_name}")
    print(f"  Modality      : {modality_str}")
    print(f"  True 3D volume: {is_3d}")
    print(f"  Cardiac task  : {is_cardiac}")
    print()
    if is_cardiac:
        print("VERDICT: PROCEED — Task02_Heart is cardiac MRI, a true 3D volume.")
        print("  -> Feed through the existing 3D volume pipeline.")
        print("  -> Reconstruct from the expert mask (label-based marching cubes).")
        print("  -> Add as a clearly-labeled secondary AR exhibit.")
        print("  -> CAMUS beating-LV + EF remains the HERO demo.")
    else:
        print(f"VERDICT: STOP — {task_name} is NOT cardiac.")
        print(f"  Modality: {modality_str}. This is real 3D anatomy, but off-theme")
        print("  for a cardiac AR demo. Wiring random organs into a heart project")
        print("  scatters the pitch. Do NOT add to the hero demo.")
        print("  -> Only proceed if the user explicitly requests it.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
