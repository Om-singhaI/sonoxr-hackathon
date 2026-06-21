"""Stage 4 — Meshing / export.

Take raw marching-cubes geometry and turn it into a clean, smooth, decimated
mesh exported as a mobile-AR-friendly .glb.

Steps:
  1. Build a trimesh.Trimesh and run basic cleanup (merge dupes, drop
     degenerate faces, fix winding/normals).
  2. Taubin smoothing — shrink-free smoothing (unlike plain Laplacian) so the
     organ keeps its proportions instead of collapsing.
  3. Quadric decimation to a target triangle budget (~30-80k) for AR. Backed by
     `fast_simplification`; if that wheel is missing we KEEP the full mesh and
     log loudly rather than crash.
  4. Recenter to the origin (nice default pose for an AR anchor) and export GLB.

Voxel spacing was already baked into the vertices in stage 3, so proportions
(and the reported size/volume) are in real millimetres.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import trimesh

log = logging.getLogger("sonoxr.meshing")

TARGET_MIN_TRIS = 30_000
TARGET_MAX_TRIS = 80_000
DECIMATE_TO = 50_000          # aim for the middle of the AR-friendly band


@dataclass
class MeshStats:
    path: str
    n_vertices: int
    n_faces: int
    watertight: bool
    extents_mm: tuple              # (dx, dy, dz) bounding box in mm
    volume_mm3: float              # mesh-enclosed volume (0 if not watertight)
    surface_area_mm2: float
    decimated: bool
    detail: str
    meta: dict = field(default_factory=dict)


def build_and_export(verts: np.ndarray, faces: np.ndarray,
                     out_path: str, normals: np.ndarray | None = None,
                     smooth_iterations: int = 10) -> MeshStats:
    """Build -> clean -> smooth -> decimate -> recenter -> export GLB."""
    mesh = trimesh.Trimesh(vertices=np.asarray(verts), faces=np.asarray(faces),
                           vertex_normals=normals, process=True)

    # --- 1. Cleanup ----------------------------------------------------------
    mesh.remove_unreferenced_vertices()
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    # Keep only the largest connected body if marching cubes left specks.
    try:
        bodies = mesh.split(only_watertight=False)
        if len(bodies) > 1:
            mesh = max(bodies, key=lambda m: len(m.faces))
            log.info("Kept largest of %d mesh bodies.", len(bodies))
    except Exception as e:
        log.warning("Mesh split skipped (%s).", e)

    # --- 2. Taubin smoothing (shrink-free) -----------------------------------
    try:
        trimesh.smoothing.filter_taubin(mesh, lamb=0.5, nu=-0.53,
                                         iterations=smooth_iterations)
    except Exception as e:
        log.warning("Taubin smoothing failed (%s); using unsmoothed mesh.", e)

    # --- 3. Quadric decimation to AR budget ----------------------------------
    decimated = False
    n_before = len(mesh.faces)
    if n_before > TARGET_MAX_TRIS:
        decimated = _decimate(mesh_ref := [mesh], DECIMATE_TO)
        mesh = mesh_ref[0]
    else:
        log.info("Mesh has %d faces (<= %d) — no decimation needed.",
                 n_before, TARGET_MAX_TRIS)

    # --- 4. Fix normals + recenter to origin ---------------------------------
    mesh.fix_normals()
    mesh.apply_translation(-mesh.centroid)

    # --- 5. Export GLB -------------------------------------------------------
    mesh.export(out_path, file_type="glb")

    extents = tuple(round(float(e), 2) for e in mesh.extents)
    volume = float(mesh.volume) if mesh.is_watertight else 0.0
    stats = MeshStats(
        path=out_path,
        n_vertices=int(len(mesh.vertices)),
        n_faces=int(len(mesh.faces)),
        watertight=bool(mesh.is_watertight),
        extents_mm=extents,
        volume_mm3=round(abs(volume), 2),
        surface_area_mm2=round(float(mesh.area), 2),
        decimated=decimated,
        detail=(f"GLB exported: {len(mesh.vertices)} verts / {len(mesh.faces)} "
                f"faces; smoothed (Taubin x{smooth_iterations})"
                + ("; decimated." if decimated else "; no decimation.")),
        meta={"faces_before_decimation": n_before},
    )
    log.info("build_and_export -> %s (%d faces, watertight=%s)",
             out_path, stats.n_faces, stats.watertight)
    return stats


def _decimate(mesh_ref: list, target_faces: int) -> bool:
    """Quadric-decimate mesh_ref[0] in place. Returns True if it actually ran.

    trimesh delegates to `fast_simplification`. If that is missing or the call
    fails, we keep the full-resolution mesh (still a valid GLB, just heavier)
    and FLAG it — never crash the export.
    """
    mesh = mesh_ref[0]
    try:
        # trimesh 4.x signature: simplify_quadric_decimation(face_count=...)
        reduced = mesh.simplify_quadric_decimation(face_count=target_faces)
        if reduced is not None and len(reduced.faces) > 0:
            mesh_ref[0] = reduced
            log.info("Decimated %d -> %d faces.", len(mesh.faces), len(reduced.faces))
            return True
        log.warning("Decimation returned empty mesh; keeping original.")
        return False
    except Exception as e:
        log.warning("Quadric decimation unavailable/failed (%s) — keeping full "
                    "mesh (%d faces). [install fast-simplification to enable]",
                    e, len(mesh.faces))
        return False
