"""Stage 2 — Segmentation.

Isolate the anatomy from background/speckle.

  * segment_volume()  -> PRIMARY 3D path: Otsu threshold + 3D morphology +
                         largest-connected-component. Output is a clean 3D
                         binary mask, ready for marching cubes.
  * segment_frames()  -> FALLBACK 2D path: per-frame Otsu + morphology
                         (OpenCV / scipy). Robustness only.

Both paths also compute a CONFIDENCE PROXY (per region / per slice). We do NOT
have ground-truth labels, so confidence is a *relative* score built from three
cheap, explainable signals:

    1. boundary sharpness  — how crisp is the intensity edge at the mask border?
                             (blurry borders => the segmenter was guessing)
    2. component stability — does one component dominate, or is it fragmented?
                             (fragmentation => speckle leaking into the mask)
    3. threshold ambiguity — how many voxels sit right on the Otsu threshold?
                             (lots of borderline voxels => an ambiguous cut)

These are normalized across the volume so the OUTPUT tells you which regions are
*less* trustworthy than the rest. That is exactly what the narration stage needs
in order to honestly flag "this region was harder to capture; consider a re-scan."

The optional pretrained-model upgrade (nnU-Net / U-Net) is stubbed in
`try_load_segmentation_model()` — it is wrapped so a missing checkpoint NEVER
blocks the threshold path. See the LOUD FLAG there.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi
from skimage.filters import threshold_otsu

log = logging.getLogger("sonoxr.segmentation")


@dataclass
class SegResult:
    mask: np.ndarray            # bool array; 3D (z,y,x) for volume, list-stack for 2D
    confidence: dict            # see _build_confidence()
    mode: str                   # "PRIMARY" or "FALLBACK"
    method: str                 # "otsu_3d" | "otsu_2d_perframe" | "model_unet"
    detail: str
    meta: dict = field(default_factory=dict)


# Confidence below this (0..1) is reported as a region worth re-scanning.
LOW_CONF_THRESHOLD = 0.55


# =============================================================================
# Optional pretrained-model upgrade  (STRETCH — assume it does NOT load)
# =============================================================================
def try_load_segmentation_model():
    """Attempt to load a pretrained ultrasound segmentation model (e.g. a U-Net /
    nnU-Net trained on a public US dataset).

    !!! LOUD FLAG !!!  THIS IS A STUB. There are no bundled weights. Drop a real
    checkpoint in app/models/ and implement loading here to upgrade segmentation.
    Until then this returns None and the pipeline uses the Otsu threshold path.
    We NEVER block on or crash because of this.
    """
    try:
        # e.g.:
        #   import torch
        #   model = torch.load("app/models/us_unet.pt", map_location="cpu")
        #   model.eval(); return model
        raise FileNotFoundError("no bundled segmentation checkpoint (expected)")
    except Exception as e:
        log.info("Pretrained segmentation model not loaded (%s). "
                 "Using Otsu threshold path. [STRETCH UPGRADE — wire weights here]", e)
        return None


# =============================================================================
# PRIMARY — 3D volume segmentation
# =============================================================================
def segment_volume(volume: np.ndarray, spacing=(1.0, 1.0, 1.0),
                   ultrasound: bool = False) -> SegResult:
    """Threshold + 3D morphological cleanup + largest connected component.

    Returns a clean boolean mask plus a per-region confidence proxy.

    `ultrasound=True` applies a US-tuned cleanup (a larger morphological closing
    to bridge residual speckle gaps). The volume passed in should already be
    DENOISED by app/preprocessing.py. With `ultrasound=False` (CT/MRI) the code
    path is byte-for-byte the validated original — no regression.
    """
    vol = volume.astype(np.float32)

    # US needs a larger closing to bridge speckle gaps; CT/MRI keeps iterations=1.
    close_iter = 2 if ultrasound else 1

    # --- 1. Threshold. Otsu on a subsample (fast + robust). Foreground = bright.
    thresh = _otsu_threshold(vol)
    fg = vol > thresh

    # Guard against degenerate thresholds (near-empty / near-full masks): fall
    # back to a high percentile so we always get a usable foreground.
    frac = float(fg.mean())
    if frac < 0.001 or frac > 0.6:
        thresh = float(np.percentile(vol, 75))
        fg = vol > thresh
        log.info("Otsu gave degenerate mask (frac=%.3f); using 75th-pct threshold.", frac)

    # --- 2. 3D morphological cleanup: close small gaps, fill holes, open speckle.
    structure = ndi.generate_binary_structure(3, 1)  # 6-connectivity
    fg = ndi.binary_closing(fg, structure=structure, iterations=close_iter)
    fg = ndi.binary_fill_holes(fg)
    fg = ndi.binary_opening(fg, structure=structure, iterations=1)

    # --- 3. Keep the largest connected component (drops background speckle).
    mask, n_components, largest_frac = _largest_component(fg)

    if mask.sum() == 0:
        # Extreme degenerate case — never let segmentation return an empty mask
        # (would crash marching cubes). Flag it; reconstruction also guards.
        log.warning("Segmentation produced an EMPTY mask; downstream will fall back.")

    confidence = _build_confidence_3d(vol, mask, thresh)
    tag = "US-tuned (closing x2, on denoised volume)" if ultrasound else "standard"
    detail = (f"Otsu 3D threshold + morphology [{tag}] + largest of {n_components} "
              f"components (dominant frac={largest_frac:.2f}).")
    log.info("segment_volume: %s voxels foreground [PRIMARY, ultrasound=%s]",
             int(mask.sum()), ultrasound)
    return SegResult(mask=mask, confidence=confidence, mode="PRIMARY",
                     method="otsu_3d_us" if ultrasound else "otsu_3d", detail=detail,
                     meta={"threshold": thresh, "n_components": n_components,
                           "spacing": spacing, "ultrasound": ultrasound})


def _otsu_threshold(vol: np.ndarray) -> float:
    """Otsu threshold on a (possibly subsampled) volume; robust to flat inputs."""
    flat = vol[np.isfinite(vol)]
    if flat.size == 0 or float(flat.max() - flat.min()) < 1e-6:
        return float(flat.mean()) if flat.size else 0.0
    # Subsample big volumes for speed — Otsu only needs the histogram shape.
    if flat.size > 2_000_000:
        flat = flat[:: max(1, flat.size // 2_000_000)]
    try:
        return float(threshold_otsu(flat))
    except Exception as e:
        log.warning("threshold_otsu failed (%s); using mean.", e)
        return float(flat.mean())


def _largest_component(binary: np.ndarray):
    """Return (mask of largest component, n_components, largest_fraction)."""
    labels, n = ndi.label(binary)
    if n == 0:
        return binary, 0, 0.0
    counts = np.bincount(labels.ravel())
    counts[0] = 0  # ignore background label
    biggest = int(counts.argmax())
    mask = labels == biggest
    largest_frac = float(counts[biggest] / max(1, binary.sum()))
    return mask, int(n), largest_frac


# =============================================================================
# Confidence proxy (3D)
# =============================================================================
def _build_confidence_3d(vol: np.ndarray, mask: np.ndarray, thresh: float) -> dict:
    """Compute per-slice confidence, then bin into 3 anatomical regions along z.

    All three signals are normalized *relative to this volume*, so the result
    highlights which regions are less reliable than the others — the honest
    uncertainty signal the narration stage flags.
    """
    z_dim = vol.shape[0]
    intensity_range = float(vol.max() - vol.min()) or 1.0
    # Band (in intensity units) used to measure "how many voxels are borderline".
    band = 0.05 * intensity_range

    present = []  # (z, sharpness_raw, stability, ambiguity_raw)
    for z in range(z_dim):
        m = mask[z]
        if not m.any():
            continue
        # boundary = mask minus its erosion -> the 1-voxel-thick border.
        border = m ^ ndi.binary_erosion(m)
        if not border.any():
            continue
        grad = ndi.gaussian_gradient_magnitude(vol[z], sigma=1.0)
        sharpness = float(grad[border].mean())
        # component stability: largest 2D component / total mask area in slice.
        lbl, n = ndi.label(m)
        if n == 0:
            stability = 0.0
        else:
            c = np.bincount(lbl.ravel())
            c[0] = 0
            stability = float(c.max() / max(1, m.sum()))
        # ambiguity: fraction of in-mask voxels whose intensity sits in the
        # threshold band (i.e. could plausibly have gone either way).
        vals = vol[z][m]
        ambiguity = float(np.mean(np.abs(vals - thresh) < band)) if vals.size else 1.0
        present.append((z, sharpness, stability, ambiguity))

    if not present:
        return {"overall": 0.0, "per_region": [], "low_confidence_regions": [],
                "method": "boundary_sharpness+stability+ambiguity",
                "note": "Empty mask — no confidence could be computed."}

    arr = np.array([[p[1], p[2], p[3]] for p in present], dtype=np.float32)
    zs = np.array([p[0] for p in present])
    sharp_norm = _norm(arr[:, 0])             # higher = sharper = better
    stability = np.clip(arr[:, 1], 0, 1)      # already 0..1, higher better
    ambig_norm = _norm(arr[:, 2])             # higher = more ambiguous = worse

    slice_conf = 0.5 * sharp_norm + 0.3 * stability + 0.2 * (1.0 - ambig_norm)
    slice_conf = np.clip(slice_conf, 0.0, 1.0)

    # Bin present slices into 3 regions along the depth (z) axis.
    region_names = ["upper portion", "central portion", "lower portion"]
    per_region = []
    edges = np.linspace(zs.min(), zs.max() + 1, 4)
    for i, name in enumerate(region_names):
        sel = (zs >= edges[i]) & (zs < edges[i + 1])
        if not sel.any():
            continue
        conf = float(slice_conf[sel].mean())
        per_region.append({
            "region": name,
            "z_range": [int(edges[i]), int(edges[i + 1])],
            "confidence": round(conf, 3),
            "label": _conf_label(conf),
        })

    low = [r["region"] for r in per_region if r["confidence"] < LOW_CONF_THRESHOLD]
    overall = float(slice_conf.mean())
    return {
        "overall": round(overall, 3),
        "overall_label": _conf_label(overall),
        "per_region": per_region,
        "low_confidence_regions": low,
        "method": "boundary_sharpness+stability+ambiguity (relative, no ground truth)",
        "n_slices_scored": len(present),
    }


def _norm(x: np.ndarray) -> np.ndarray:
    """Min-max normalize to 0..1; returns mid value if all-equal."""
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-9:
        return np.full_like(x, 0.5)
    return (x - lo) / (hi - lo)


def _conf_label(c: float) -> str:
    return "high" if c >= 0.7 else ("medium" if c >= LOW_CONF_THRESHOLD else "low")


# =============================================================================
# FALLBACK — per-frame 2D segmentation (robustness only)
# =============================================================================
def segment_frames(frames: list[np.ndarray]) -> SegResult:
    """Per-frame Otsu + morphology + largest 2D component. Stacks into a 3D mask.

    ROBUSTNESS ONLY — produced from unregistered frames, so the resulting mask
    is not anatomically faithful. The confidence reported here is per-frame.
    """
    masks = []
    confs = []
    structure = ndi.generate_binary_structure(2, 1)
    for f in frames:
        f = f.astype(np.float32)
        try:
            t = threshold_otsu(f) if float(f.max() - f.min()) > 1e-6 else f.mean()
        except Exception:
            t = float(f.mean())
        m = f > t
        m = ndi.binary_closing(m, structure=structure)
        m = ndi.binary_fill_holes(m)
        m = ndi.binary_opening(m, structure=structure)
        m, n, _frac = _largest_component(m)
        masks.append(m)
        # Cheap per-frame confidence: sharpness at border, relative within frame.
        if m.any():
            border = m ^ ndi.binary_erosion(m)
            grad = ndi.gaussian_gradient_magnitude(f, sigma=1.0)
            confs.append(float(grad[border].mean()) if border.any() else 0.0)
        else:
            confs.append(0.0)

    mask = np.stack(masks, axis=0) if masks else np.zeros((1, 1, 1), bool)
    cn = _norm(np.array(confs)) if confs else np.array([0.0])
    overall = float(cn.mean())
    confidence = {
        "overall": round(overall, 3),
        "overall_label": _conf_label(overall),
        "per_region": [{"region": "whole stack", "confidence": round(overall, 3),
                        "label": _conf_label(overall)}],
        "low_confidence_regions": ["whole stack"] if overall < LOW_CONF_THRESHOLD else [],
        "method": "per-frame Otsu sharpness (2D fallback)",
        "n_frames": len(frames),
        "WARNING": "2D fallback: frames are unregistered; mask is not anatomically faithful.",
    }
    log.warning("segment_frames: 2D FALLBACK over %d frames (low fidelity).", len(frames))
    return SegResult(mask=mask, confidence=confidence, mode="FALLBACK",
                     method="otsu_2d_perframe",
                     detail=f"Per-frame Otsu+morphology over {len(frames)} frames.",
                     meta={})
