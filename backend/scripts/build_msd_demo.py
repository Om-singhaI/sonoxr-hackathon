#!/usr/bin/env python3
"""Iteration 7b — Build the MSD Task02_Heart (left atrium) secondary AR exhibit.

Reconstructs a left-atrium mesh from the expert MSD segmentation mask (label 1)
using the existing 3D pipeline (marching cubes -> Taubin smooth -> decimate -> GLB).
This is a SECONDARY exhibit proving the pipeline is modality-agnostic. The CAMUS
beating-LV + EF demo is and remains the HERO.

Honesty:
  - MRI, NOT ultrasound
  - Left atrium, NOT the LV or the whole heart
  - Reconstructed from expert labels, NOT raw MRI intensity
  - NO EF (MSD Task02_Heart has no EF annotation)

Cite: Medical Segmentation Decathlon, medicaldecathlon.com
      Antonelli et al., Nature Communications 13, 4128, 2022.
      CC-BY-SA 4.0 licence.

    python scripts/build_msd_demo.py [la_003]
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import SimpleITK as sitk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.reconstruction import reconstruct_from_volume
from app.meshing import build_and_export
from app import narration

import render_preview as rp
import trimesh

DATA     = os.path.join(ROOT, "data")
BACK     = os.path.join(ROOT, "demo", "golden_msd")
FRONT    = os.path.join(ROOT, "frontend", "golden_msd")
CITATION = ("Medical Segmentation Decathlon — medicaldecathlon.com. "
            "M. Antonelli et al., 'The Medical Segmentation Decathlon,' "
            "Nature Communications 13, 4128, 2022. Licence: CC-BY-SA 4.0.")
METHOD   = ("Left atrium reconstructed from MSD Task02_Heart expert MRI "
            "segmentation mask (label 1) via marching cubes — true 3D volume, "
            "real MRI voxel spacing. NOT ultrasound. NOT EF-capable.")
ANATOMY  = "left atrium (cardiac MRI — MSD Task02_Heart)"


def find_task_dir() -> str:
    for dirpath, dirnames, filenames in os.walk(DATA):
        if "dataset.json" in filenames and "imagesTr" in dirnames:
            return dirpath
    raise FileNotFoundError("MSD Task02_Heart not found under data/.")


def load_mask(task_dir: str, vol_id: str) -> tuple[np.ndarray, tuple]:
    path = os.path.join(task_dir, "labelsTr", f"{vol_id}.nii.gz")
    img  = sitk.ReadImage(path)
    arr  = sitk.GetArrayFromImage(img)        # (Z, Y, X), int
    sp   = img.GetSpacing()                   # (X, Y, Z)
    spacing_zyx = (float(sp[2]), float(sp[1]), float(sp[0]))
    return arr, spacing_zyx


def main() -> int:
    os.makedirs(BACK,  exist_ok=True)
    os.makedirs(FRONT, exist_ok=True)

    vol_id   = (sys.argv[1] if len(sys.argv) > 1 else "la_003").replace(".nii.gz", "")
    task_dir = find_task_dir()
    print(f"Task dir  : {task_dir}")
    print(f"Volume    : {vol_id}")

    # --- load mask, extract left atrium (label 1) ---
    mask_full, spacing = load_mask(task_dir, vol_id)
    lv_mask = (mask_full == 1).astype(np.uint8)
    n_vox = int(lv_mask.sum())
    print(f"Mask shape: {mask_full.shape}  spacing(z,y,x)={tuple(round(s,3) for s in spacing)} mm")
    print(f"Left atrium voxels: {n_vox}")
    if n_vox < 100:
        print("ERROR: left-atrium mask is empty — check the volume id.", file=sys.stderr)
        return 1

    # --- reconstruct: marching cubes on the REAL 3D mask ---
    print("Reconstructing left atrium mesh …")
    recon = reconstruct_from_volume(lv_mask, spacing=spacing)
    print(f"  {len(recon.verts)} verts / {len(recon.faces)} faces  [{recon.mode}]")

    # --- mesh: smooth + decimate -> GLB ---
    glb_path = os.path.join(FRONT, "model.glb")
    print("Meshing (smooth + decimate + export GLB) …")
    stats = build_and_export(recon.verts, recon.faces, glb_path,
                             normals=recon.normals, smooth_iterations=10)
    print(f"  {stats.n_faces} faces  watertight={stats.watertight}")
    print(f"  extents(mm): {stats.extents_mm}")
    print(f"  volume(mm³): {stats.volume_mm3}  ({stats.volume_mm3/1000:.1f} cm³)")

    # copy to demo/
    import shutil
    shutil.copyfile(glb_path, os.path.join(BACK, "model.glb"))

    # --- narration ---
    summary = {
        "anatomy_label": ANATOMY,
        "modality": "MRI (cardiac MRI, not ultrasound)",
        "task": "MSD Task02_Heart — left atrium segmentation",
        "volume_id": vol_id,
        "voxel_count": n_vox,
        "spacing_mm_zyx": [round(s, 3) for s in spacing],
        "mesh_faces": stats.n_faces,
        "mesh_volume_cm3": round(stats.volume_mm3 / 1000, 1),
        "extents_mm": list(stats.extents_mm),
        "method": METHOD,
    }
    narr = narration.narrate_msd(summary)

    # --- preview render ---
    preview_path = os.path.join(ROOT, "preview", "msd_la_ed.png")
    mesh = trimesh.load(glb_path, force="mesh")
    fn   = mesh.face_normals
    rp.render_turntable(mesh, preview_path,
                        rp._shade(fn, rp.TISSUE),
                        f"MSD Task02_Heart — left atrium ({vol_id}) | "
                        f"{stats.volume_mm3/1000:.0f} cm³")

    # --- freeze meta ---
    meta = {
        "data_source": "REAL",
        "modality": "3D cardiac MRI (MSD Task02_Heart — left atrium)",
        "task": "Task02_Heart",
        "anatomy": "left atrium",
        "volume_id": vol_id,
        "spacing_mm_zyx": [round(s, 3) for s in spacing],
        "mesh_faces": stats.n_faces,
        "mesh_volume_cm3": round(stats.volume_mm3 / 1000, 1),
        "extents_mm": list(stats.extents_mm),
        "watertight": stats.watertight,
        "recon_mode": recon.mode,
        "method": METHOD,
        "citation": CITATION,
        "is_synthetic_placeholder": False,
        "narration": narr["text"],
        "narration_mode": narr["mode"],
        "narration_model": narr["model"],
        "confidence_note": ("Reconstructed from expert MRI segmentation labels — "
                            "mesh geometry is reliable. Intensity-based artifacts "
                            "are absent (mask-only reconstruction). Not a medical device."),
    }
    for d in (FRONT, BACK):
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2)

    print(f"\nnarration[{narr['mode']}]: {narr['text']}")
    print(f"GLB       -> {glb_path}")
    print(f"preview   -> {preview_path}")
    print(f"frozen    -> {FRONT}/ + {BACK}/")
    print(f"volume    : {stats.volume_mm3/1000:.1f} cm³  (left atrium, normal ~25–50 cm³)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
