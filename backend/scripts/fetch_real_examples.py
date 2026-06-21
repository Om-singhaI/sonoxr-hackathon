#!/usr/bin/env python3
"""Fetch TWO REAL public volumetric datasets, run the full pipeline on each,
and render the results.

These are genuine scientific scan volumes from the scikit-image data archive
(fetched via pooch over the network on first run, then cached):

  1. brain_mri   — a real T1 MRI of a human brain   (skimage.data.brain,   10x256x256)
  2. cell_nuclei — a real 3D confocal microscopy stack of cell nuclei
                   (skimage.data.cells3d nuclei channel, 60x256x256)

They are NOT ultrasound — but they ARE real volumetric scans, so they exercise
the exact PRIMARY path (volume -> 3D segmentation -> marching cubes -> GLB ->
narration) the demo uses, on real anatomy/biology instead of the synthetic
placeholder. Outputs land in ./preview/ and the jobs are real (is_synthetic=False).

    python scripts/fetch_real_examples.py
"""

from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import SimpleITK as sitk

from app import pipeline
import scripts.render_preview as rp  # reuse the renderer

REAL_DIR = os.path.join(ROOT, "data", "sample", "real")


def save_nifti(volume: np.ndarray, spacing_zyx, out_path: str) -> str:
    """Write a (z,y,x) volume to NIfTI with the given spacing (preserved on read)."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img = sitk.GetImageFromArray(volume.astype(np.float32))
    sz, sy, sx = spacing_zyx
    img.SetSpacing((float(sx), float(sy), float(sz)))   # sitk wants (x, y, z)
    sitk.WriteImage(img, out_path)
    return out_path


def fetch_ct_head() -> np.ndarray:
    """Download the classic Stanford CThead — a REAL 113-slice human head CT.

    Distributed as a gz-tar of 113 raw slices (256x256, 16-bit big-endian). This
    is a genuinely DEEP volume (hundreds-of-slices class), so it reconstructs into
    a recognizable 3D head — the counter-example to thin/under-sampled volumes.
    Cached under data/sample/real/ct_head/_slices after the first download.
    """
    import glob, io, tarfile, urllib.request

    url = "https://graphics.stanford.edu/data/voldata/CThead.tar.gz"
    raw_dir = os.path.join(REAL_DIR, "ct_head", "_slices")
    have = glob.glob(os.path.join(raw_dir, "CThead.*"))
    if not have:
        os.makedirs(raw_dir, exist_ok=True)
        print(f"  downloading CThead from {url} ...")
        data = urllib.request.urlopen(url, timeout=180).read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            tf.extractall(raw_dir)
    files = sorted((f for f in glob.glob(os.path.join(raw_dir, "CThead.*"))
                    if f.rsplit(".", 1)[-1].isdigit()),
                   key=lambda p: int(p.rsplit(".", 1)[-1]))
    slices = [np.frombuffer(open(f, "rb").read(), dtype=">u2").reshape(256, 256)
              for f in files]
    return np.stack(slices, 0).astype(np.float32)


def fetch_examples():
    """Return [(name, volume(z,y,x), spacing_zyx, label, units)]."""
    import skimage.data as d

    examples = []

    # 0) DEEP real volume — a 113-slice human head CT (recognizable 3D anatomy).
    examples.append(("ct_head", fetch_ct_head(), (1.5, 1.0, 1.0),
                     "a real human head CT (113-slice volume)", "mm"))

    # 1) Real brain MRI (T1). 10 slices -> assume a thick slice spacing so the
    #    head keeps believable proportions (the array carries no header spacing).
    brain = d.brain().astype(np.float32)                # (10, 256, 256) uint16
    examples.append(("brain_mri", brain, (5.0, 1.0, 1.0),
                     "a real human brain MRI (T1)", "mm"))

    # 2) Real confocal microscopy — nuclei channel (channel 1) of cells3d.
    cells = d.cells3d().astype(np.float32)              # (60, 2, 256, 256)
    nuclei = cells[:, 1, :, :]                          # (60, 256, 256)
    examples.append(("cell_nuclei", nuclei, (0.29, 0.26, 0.26),
                     "a real cell nucleus from a 3D confocal microscopy stack", "um"))

    return examples


def run_one(name: str, volume, spacing_zyx, label: str, units: str):
    print("\n" + "=" * 72)
    print(f"REAL EXAMPLE: {name}  ({label})")
    print(f"  volume shape (z,y,x) = {volume.shape}, spacing = {spacing_zyx} {units}")

    nii = save_nifti(volume, spacing_zyx,
                     os.path.join(REAL_DIR, name, f"{name}.nii.gz"))
    job_id = pipeline.create_job(
        input_type="nifti_volume", source_path=nii,
        anatomy_label=label, is_synthetic_placeholder=False)   # REAL data
    status = pipeline.run_pipeline(job_id)

    print(f"  job {job_id}: status={status['status']}")
    for s, info in status["stages"].items():
        print(f"    {s:14} {info['status']:6} mode={info['mode']}")

    # Render the result (clean + uncertainty overlay) with name-prefixed files.
    mesh, _job, low = rp.get_mesh_for_job(job_id)
    if len(mesh.faces) > 12000:
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=12000)
        except Exception:
            pass
    fn = mesh.face_normals
    clean = rp._shade(fn, rp.TISSUE)
    rp.render_turntable(mesh, os.path.join(rp.PREVIEW_DIR, f"{name}_turntable.png"),
                        clean, f"REAL DATA — {label} ({units})")
    colors = clean.copy()
    if low:
        m = rp.low_region_face_mask(mesh, low)
        colors[m] = rp._shade(fn[m], rp.AMBER)
    rp.render_turntable(mesh, os.path.join(rp.PREVIEW_DIR, f"{name}_overlay.png"),
                        colors, f"REAL DATA — uncertainty overlay ({name})")

    # Report narration + confidence.
    import json
    narr = json.load(open(pipeline.narration_path(job_id)))
    conf = narr["summary"]["confidence"]
    size = narr["summary"]["approx_size"]
    print(f"  size: ~{size['segmented_volume_cm3']} (volume units^3 from spacing); "
          f"bbox(mm-as-set)={size['bounding_box_mm']}")
    print(f"  confidence overall={conf['overall']} ({conf['overall_label']}); "
          f"low regions={conf['low_confidence_regions'] or 'none'}")
    print(f"  narration[{narr['mode']}]: {narr['narration']}")
    return job_id


def main():
    os.makedirs(rp.PREVIEW_DIR, exist_ok=True)
    for name, vol, sp, label, units in fetch_examples():
        run_one(name, vol, sp, label, units)
    print("\nDone. Renders in ./preview/ (brain_mri_*.png, cell_nuclei_*.png)")


if __name__ == "__main__":
    raise SystemExit(main())
