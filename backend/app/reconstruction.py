"""Stage 3 — 3D reconstruction (mask -> surface vertices/faces/normals).

PRIMARY (the demo path):
    reconstruct_from_volume() runs marching cubes on the REAL 3D mask using REAL
    voxel spacing. Because the depth axis is real, the surface is recognizable
    anatomy — not a blob.

ROBUSTNESS FALLBACK:
    reconstruct_from_frames_voxel_stack() runs the same marching cubes on a mask
    built from unregistered 2D frames stacked with UNIFORM (fabricated) spacing.
    This is LOW FIDELITY by construction and is NOT for the demo — flagged loudly.

STRETCH UPGRADE (assume it FAILS — never let the demo depend on it):
    try_ultrasodm() shells out to the UltrasODM 2D-sweep reconstruction repo in a
    subprocess with a hard 60s timeout and full try/except. If it yields a point
    cloud, poisson_from_pointcloud() (Open3D) can surface it. Both fail silently
    back to the volume/voxel path.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi
from skimage import measure

log = logging.getLogger("sonoxr.reconstruction")


@dataclass
class ReconResult:
    verts: np.ndarray           # (N, 3) float, in millimetres (spacing applied)
    faces: np.ndarray           # (M, 3) int
    normals: np.ndarray         # (N, 3) float
    mode: str                   # "PRIMARY" or "FALLBACK"
    detail: str
    meta: dict = field(default_factory=dict)


# =============================================================================
# PRIMARY — marching cubes on a real volumetric mask
# =============================================================================
def reconstruct_from_volume(mask: np.ndarray, spacing=(1.0, 1.0, 1.0),
                            iso_level: float = 0.5) -> ReconResult:
    """Surface a 3D binary mask with marching cubes, honoring voxel spacing.

    We lightly Gaussian-smooth the binary mask to a soft field before marching
    cubes so the iso-surface is smooth instead of voxel-staircased; Taubin
    smoothing in the meshing stage finishes the job. Spacing makes the result
    correctly proportioned in millimetres.
    """
    voxel_count = int(mask.sum())
    if voxel_count < 8:
        raise ValueError("Mask too small / empty for marching cubes.")

    verts, faces, normals = _marching_cubes(mask, spacing, iso_level)
    detail = (f"Marching cubes on real volume mask ({voxel_count} voxels, "
              f"spacing(z,y,x)={tuple(round(s,3) for s in spacing)} mm).")
    log.info("reconstruct_from_volume: %d verts / %d faces [PRIMARY]",
             len(verts), len(faces))
    return ReconResult(verts=verts, faces=faces, normals=normals, mode="PRIMARY",
                       detail=detail,
                       meta={"voxel_count": voxel_count, "spacing": spacing})


def _marching_cubes(mask: np.ndarray, spacing, iso_level: float):
    """Shared marching-cubes core. `spacing` is (sz, sy, sx) in mm."""
    soft = ndi.gaussian_filter(mask.astype(np.float32), sigma=1.0)
    # Guard: iso_level must lie within the field's value range.
    lo, hi = float(soft.min()), float(soft.max())
    level = iso_level if lo < iso_level < hi else 0.5 * (lo + hi)
    verts, faces, normals, _vals = measure.marching_cubes(
        soft, level=level, spacing=spacing)
    return (verts.astype(np.float32), faces.astype(np.int64),
            normals.astype(np.float32))


# =============================================================================
# ROBUSTNESS FALLBACK — uniform-spacing voxel stack
# =============================================================================
def reconstruct_from_frames_voxel_stack(mask_stack: np.ndarray,
                                        spacing=(1.0, 1.0, 1.0)) -> ReconResult:
    """Marching cubes over a stack of 2D masks with UNIFORM (fabricated) depth.

    !!! LOW FIDELITY — NOT FOR THE DEMO !!!
    The frames were never spatially registered, so the depth axis here is
    invented. The mesh is a rough impression at best. This exists purely so an
    arbitrary 2D upload still returns *something* instead of crashing.
    """
    voxel_count = int(mask_stack.sum())
    if voxel_count < 8:
        raise ValueError("2D-stack mask too small / empty for marching cubes.")
    verts, faces, normals = _marching_cubes(mask_stack, spacing, 0.5)
    log.warning("reconstruct_from_frames_voxel_stack: LOW-FIDELITY 2D FALLBACK "
                "(%d verts) — fabricated depth axis.", len(verts))
    return ReconResult(
        verts=verts, faces=faces, normals=normals, mode="FALLBACK",
        detail="Uniform-spacing voxel stack + marching cubes (LOW FIDELITY, "
               "fabricated depth axis — not for demo).",
        meta={"voxel_count": voxel_count, "fabricated_depth_axis": True})


# =============================================================================
# STRETCH UPGRADE — UltrasODM 2D-sweep reconstruction (assume it FAILS)
# =============================================================================
def try_ultrasodm(input_path: str, timeout: int = 60):
    """Attempt UltrasODM (https://github.com/AnandMayank/UltrasODM) in a subprocess.

    !!! LOUD FLAG !!!  This is EXPECTED TO FAIL in the demo environment — the repo
    has Mamba/conda deps and checkpoints we do not bundle. It runs in a subprocess
    with a hard timeout and full try/except, and ALWAYS returns None on any
    problem so the caller falls back silently to the volume/voxel path.

    Returns a point cloud as an (N,3) numpy array on success, else None.
    """
    runner = os.environ.get("ULTRASODM_RUNNER")  # e.g. path to a wrapper script
    if not runner or not os.path.exists(runner):
        log.info("UltrasODM runner not configured/found — skipping STRETCH path. "
                 "[set ULTRASODM_RUNNER to a wrapper script to enable]")
        return None
    try:
        out_npy = input_path + ".ultrasodm_points.npy"
        # The wrapper is expected to write an (N,3) .npy point cloud to out_npy.
        proc = subprocess.run(
            [runner, "--input", input_path, "--out", out_npy],
            timeout=timeout, capture_output=True, text=True)
        if proc.returncode != 0:
            log.warning("UltrasODM exited %d: %s", proc.returncode, proc.stderr[:500])
            return None
        if not os.path.exists(out_npy):
            log.warning("UltrasODM produced no point cloud at %s.", out_npy)
            return None
        pts = np.load(out_npy)
        log.info("UltrasODM returned %d points [STRETCH SUCCESS].", len(pts))
        return pts
    except subprocess.TimeoutExpired:
        log.warning("UltrasODM timed out after %ds — falling back.", timeout)
        return None
    except Exception as e:  # never let the stretch path break the pipeline
        log.warning("UltrasODM failed (%s) — falling back.", e)
        return None


def poisson_from_pointcloud(points: np.ndarray):
    """Open3D Poisson surface reconstruction from a point cloud (STRETCH only).

    Returns (verts, faces) or None if Open3D is unavailable / it fails.
    """
    try:
        import open3d as o3d
    except Exception as e:
        log.info("Open3D not installed (%s) — cannot Poisson-reconstruct.", e)
        return None
    try:
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64))
        pcd.estimate_normals()
        mesh, _dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=8)
        verts = np.asarray(mesh.vertices, dtype=np.float32)
        faces = np.asarray(mesh.triangles, dtype=np.int64)
        log.info("Poisson reconstruction: %d verts / %d faces.", len(verts), len(faces))
        return verts, faces
    except Exception as e:
        log.warning("Poisson reconstruction failed (%s).", e)
        return None
