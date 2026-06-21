#!/usr/bin/env python3
"""Render the reconstructed .glb the way it will appear in AR.

Produces, in ./preview/:
  * organ_turntable.png            — the mesh from 4 angles (what floats in AR)
  * organ_uncertainty_overlay.png  — same mesh with the LOW-CONFIDENCE region
                                     tinted amber (the "re-scan this" overlay the
                                     narration talks about)
  * ar_preview.html + model.glb    — an interactive <model-viewer> page (orbit +
                                     a real "View in AR" button on a phone)

Run AFTER you've produced a model, or with no args to build a fresh demo job:
    python scripts/render_preview.py            # builds a /demo job, renders it
    python scripts/render_preview.py <job_id>   # render an existing job
"""

from __future__ import annotations

import os
import shutil
import sys

import numpy as np
import trimesh

import matplotlib
matplotlib.use("Agg")  # headless backend — no display needed
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PREVIEW_DIR = os.path.join(ROOT, "preview")
sys.path.insert(0, ROOT)  # so `from app import pipeline` works when run as a script

TISSUE = np.array([0.86, 0.72, 0.63])   # warm tissue base color
AMBER = np.array([0.96, 0.55, 0.16])    # low-confidence highlight
LIGHT = np.array([0.4, 0.5, 0.8])       # light direction for simple shading
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def get_mesh_for_job(job_id: str | None):
    """Return (trimesh.Trimesh, low_conf_high_z: bool) for a job, building one if needed."""
    from app import pipeline
    if job_id is None:
        job_id = pipeline.prepare_demo_job()
        pipeline.run_pipeline(job_id)
        print(f"Built demo job {job_id}")
    glb = pipeline.model_path(job_id)
    if not os.path.exists(glb):
        raise FileNotFoundError(f"No model for job {job_id} — run the pipeline first.")
    # force='mesh' concatenates the GLB scene into a single Trimesh.
    mesh = trimesh.load(glb, force="mesh")

    # Did segmentation flag a low-confidence region? (read from the narration JSON)
    low_regions = []
    import json
    npath = pipeline.narration_path(job_id)
    if os.path.exists(npath):
        summary = json.load(open(npath)).get("summary", {})
        low_regions = summary.get("confidence", {}).get("low_confidence_regions", [])
    print(f"low-confidence regions: {low_regions or 'none'}")
    return mesh, job_id, low_regions


# The confidence proxy bins present slices into these 3 equal z-bands.
REGION_ORDER = ["upper portion", "central portion", "lower portion"]


def low_region_face_mask(mesh, low_regions) -> np.ndarray:
    """Per-face boolean mask of faces falling in any flagged low-confidence band.

    Maps each named region to its z-third of the mesh (upper=low z ... lower=high
    z), matching how segmentation binned the volume. "whole stack" (the 2D
    fallback signal) flags everything.
    """
    z = mesh.vertices[:, 0]                          # marching-cubes depth axis
    face_z = z[mesh.faces].mean(axis=1)
    lo, hi = face_z.min(), face_z.max()
    edges = np.linspace(lo, hi, 4)
    mask = np.zeros(len(face_z), bool)
    for name in low_regions:
        if name in REGION_ORDER:
            i = REGION_ORDER.index(name)
            mask |= (face_z >= edges[i]) & (face_z <= edges[i + 1])
        else:
            mask[:] = True
    return mask


def _shade(face_normals: np.ndarray, base: np.ndarray) -> np.ndarray:
    """Simple lambert shading so the surface reads as 3D, not flat."""
    lit = np.clip(face_normals @ LIGHT, 0, 1)
    factor = (0.4 + 0.6 * lit)[:, None]
    return np.clip(base[None, :] * factor, 0, 1)


def render_turntable(mesh, out_path, face_colors, title):
    """4-view turntable into a single 2x2 PNG."""
    # axis 0 of marching-cubes verts is the volume depth (z); map it to the
    # vertical axis so the organ stands upright.
    V = mesh.vertices
    xyz = np.column_stack([V[:, 2], V[:, 1], V[:, 0]])
    tris = xyz[mesh.faces]

    fig = plt.figure(figsize=(9, 9), facecolor="white")
    fig.suptitle(title, fontsize=13, y=0.97)
    views = [(20, 35), (20, 125), (20, 215), (20, 305)]
    lo, hi = xyz.min(0), xyz.max(0)
    span = (hi - lo).max()
    for i, (elev, azim) in enumerate(views, 1):
        ax = fig.add_subplot(2, 2, i, projection="3d")
        pc = Poly3DCollection(tris, facecolors=face_colors, linewidths=0)
        ax.add_collection3d(pc)
        mid = (hi + lo) / 2
        ax.set_xlim(mid[0] - span / 2, mid[0] + span / 2)
        ax.set_ylim(mid[1] - span / 2, mid[1] + span / 2)
        ax.set_zlim(mid[2] - span / 2, mid[2] + span / 2)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        ax.set_title(f"view {i}  ({azim}°)", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"wrote {out_path}")


def write_model_viewer_html(glb_src: str):
    """Interactive viewer that loads the REAL .glb (orbit + AR button)."""
    shutil.copyfile(glb_src, os.path.join(PREVIEW_DIR, "model.glb"))
    html = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SonoXR — AR preview</title>
<script type="module" src="https://unpkg.com/@google/model-viewer/dist/model-viewer.min.js"></script>
<style>
  body{margin:0;background:#11151c;color:#cdd6e3;font-family:system-ui,sans-serif}
  header{padding:14px 18px}
  h1{font-size:16px;margin:0}
  p{font-size:13px;color:#8b97a8;margin:4px 0 0}
  model-viewer{width:100vw;height:80vh;background:#0c0f14}
</style></head>
<body>
  <header>
    <h1>SonoXR / EchoAR — reconstructed model</h1>
    <p>Drag to orbit. On a phone/tablet, tap <b>View in AR</b> to place it in your room (this is what the AR frontend renders).</p>
  </header>
  <model-viewer src="model.glb" alt="Reconstructed anatomy"
                camera-controls auto-rotate shadow-intensity="1"
                exposure="1.1" ar ar-modes="webxr scene-viewer quick-look">
  </model-viewer>
</body></html>
"""
    out = os.path.join(PREVIEW_DIR, "ar_preview.html")
    with open(out, "w") as f:
        f.write(html)
    print(f"wrote {out}  (open in a browser; needs internet for the model-viewer CDN)")


def main():
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    mesh, job_id, low_regions = get_mesh_for_job(job_id)

    # Decimate for snappy matplotlib rendering (the exported .glb is full-res).
    if len(mesh.faces) > 12000:
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=12000)
        except Exception as e:
            print(f"(preview decimation skipped: {e})")
    print(f"rendering {len(mesh.faces)} faces, extents(mm)={[round(e,1) for e in mesh.extents]}")

    fn = mesh.face_normals

    # 1) Clean organ — what's actually visible in AR.
    clean = _shade(fn, TISSUE)
    render_turntable(mesh, os.path.join(PREVIEW_DIR, "organ_turntable.png"),
                     clean, "AR view — reconstructed anatomy (.glb)")

    # 2) Uncertainty overlay — tint the flagged low-confidence band amber.
    colors = clean.copy()
    if low_regions:
        uncertain = low_region_face_mask(mesh, low_regions)
        colors[uncertain] = _shade(fn[uncertain], AMBER)
        title = "AR overlay — amber = low-confidence region (narration: 're-scan here')"
    else:
        title = "AR overlay — no low-confidence region flagged"
    render_turntable(mesh, os.path.join(PREVIEW_DIR, "organ_uncertainty_overlay.png"),
                     colors, title)

    # 3) Interactive / real-AR viewer.
    from app import pipeline
    write_model_viewer_html(pipeline.model_path(job_id))
    print("\nDone. See ./preview/")


if __name__ == "__main__":
    raise SystemExit(main())
