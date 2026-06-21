"""Stage 1.5 — Ultrasound-aware preprocessing (NEW in iteration 2).

Real ultrasound is the hard case the rest of the pipeline was never tested on:
heavy multiplicative speckle, low contrast, acoustic shadowing, and a
log-compressed dynamic range. A single global Otsu threshold on a raw US volume
tends to produce mush. This module conditions a US volume BEFORE segmentation so
the existing Otsu + morphology + largest-CC path has a fighting chance.

It runs ONLY for ultrasound-modality inputs (see pipeline.py). CT/MRI volumes
bypass it entirely, so the already-validated CT/MRI path is untouched.

Steps (each guarded so a failure degrades, never crashes):
  1. Intensity normalization  — robust percentile rescale to a common 0-255
     range (tames the log-compressed US dynamic range / arbitrary scanner units).
  2. Speckle reduction        — edge-preserving denoise. Two real implementations,
     selected by config:
        (a) SimpleITK anisotropic diffusion (Gradient or Curvature) — PRIMARY
        (b) OpenCV fast Non-Local-Means per slice (+ median) — FALLBACK
     ...with a scipy median filter as a last-ditch fallback.
  3. Contrast handling        — optional per-slice CLAHE for low-contrast US.

Everything is CPU-only. Config via env vars (with sane defaults):
  US_DENOISE_METHOD = auto | gradient_anisotropic | curvature_anisotropic | nlm | none
  US_DENOISE_ITERS  = <int>   (anisotropic-diffusion iterations; default 5)
  US_USE_CLAHE      = 1 | 0   (default 1)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage as ndi

log = logging.getLogger("sonoxr.preprocessing")

try:
    import SimpleITK as sitk
    _HAS_SITK = True
except Exception as e:  # pragma: no cover
    _HAS_SITK = False
    log.warning("SimpleITK unavailable in preprocessing (%s); anisotropic diffusion off.", e)

try:
    import cv2
    _HAS_CV2 = True
except Exception as e:  # pragma: no cover
    _HAS_CV2 = False
    log.warning("OpenCV unavailable in preprocessing (%s); NLM/CLAHE off.", e)


@dataclass
class PreprocResult:
    volume: np.ndarray        # denoised, normalized float32 volume (z, y, x)
    method: str               # speckle-reduction method actually used (for status)
    detail: str               # human-readable pipeline of steps (for status)
    meta: dict = field(default_factory=dict)


# =============================================================================
# Step 1 — intensity normalization
# =============================================================================
def normalize_intensity(vol: np.ndarray, p_low: float = 1.0,
                        p_high: float = 99.0) -> np.ndarray:
    """Robust percentile rescale to [0, 255].

    Ultrasound arrives log-compressed and in arbitrary units; clipping at the
    1st/99th percentiles removes outliers and maps the bulk of the signal to a
    common range so a fixed denoiser/threshold behaves predictably.
    """
    v = vol.astype(np.float32)
    finite = v[np.isfinite(v)]
    if finite.size == 0:
        return np.zeros_like(v)
    lo, hi = np.percentile(finite, [p_low, p_high])
    if hi - lo < 1e-6:
        return np.zeros_like(v)
    return np.clip((v - lo) / (hi - lo), 0.0, 1.0) * 255.0


# =============================================================================
# Step 2 — speckle reduction (two real implementations + last-ditch fallback)
# =============================================================================
def reduce_speckle_anisotropic(vol: np.ndarray, flavor: str = "gradient",
                               iterations: int = 5, conductance: float = 1.5,
                               time_step: float = 0.0625) -> np.ndarray:
    """Edge-preserving anisotropic diffusion via SimpleITK (PRIMARY denoiser).

    flavor: "gradient" (Perona-Malik, faster) or "curvature" (better edge
    preservation, slower). time_step <= 0.0625 satisfies the 3D CFL stability
    condition.
    """
    if not _HAS_SITK:
        raise RuntimeError("SimpleITK not available for anisotropic diffusion")
    img = sitk.GetImageFromArray(vol.astype(np.float32))
    if flavor == "curvature":
        f = sitk.CurvatureAnisotropicDiffusionImageFilter()
    else:
        f = sitk.GradientAnisotropicDiffusionImageFilter()
    f.SetNumberOfIterations(int(iterations))
    f.SetConductanceParameter(float(conductance))
    f.SetTimeStep(float(time_step))
    out = sitk.GetArrayFromImage(f.Execute(img)).astype(np.float32)
    return out


def reduce_speckle_nlm(vol: np.ndarray) -> np.ndarray:
    """Fast Non-Local-Means per slice via OpenCV (+ light median) — FALLBACK."""
    if not _HAS_CV2:
        raise RuntimeError("OpenCV not available for NLM")
    u8 = np.clip(vol, 0, 255).astype(np.uint8)
    out = np.empty_like(vol, dtype=np.float32)
    for z in range(u8.shape[0]):
        d = cv2.fastNlMeansDenoising(u8[z], None, h=10,
                                     templateWindowSize=7, searchWindowSize=21)
        d = cv2.medianBlur(d, 3)
        out[z] = d.astype(np.float32)
    return out


def _reduce_speckle_median(vol: np.ndarray) -> np.ndarray:
    """Last-ditch dependency-free fallback so this stage never hard-fails."""
    return ndi.median_filter(vol.astype(np.float32), size=(1, 3, 3))


# =============================================================================
# Step 3 — contrast handling (optional)
# =============================================================================
def apply_clahe(vol: np.ndarray, clip_limit: float = 2.0,
                grid: int = 8) -> np.ndarray:
    """Per-slice CLAHE (Contrast-Limited Adaptive Histogram Equalization)."""
    if not _HAS_CV2:
        return vol
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid, grid))
    u8 = np.clip(vol, 0, 255).astype(np.uint8)
    out = np.empty_like(vol, dtype=np.float32)
    for z in range(u8.shape[0]):
        out[z] = clahe.apply(u8[z]).astype(np.float32)
    return out


# =============================================================================
# Orchestration
# =============================================================================
def preprocess_ultrasound(volume: np.ndarray, spacing=(1.0, 1.0, 1.0),
                          method: str | None = None,
                          use_clahe: bool | None = None) -> PreprocResult:
    """Normalize -> denoise -> (optional) CLAHE. Returns a conditioned volume.

    `method` defaults to env US_DENOISE_METHOD (default "auto"). "auto" prefers
    SimpleITK gradient anisotropic diffusion and falls back to OpenCV NLM, then
    to a median filter — so the stage always produces something.
    """
    method = (method or os.environ.get("US_DENOISE_METHOD", "auto")).lower()
    if use_clahe is None:
        use_clahe = os.environ.get("US_USE_CLAHE", "1") not in ("0", "false", "False")
    iterations = int(os.environ.get("US_DENOISE_ITERS", "5"))

    # Defensive: this path expects a 3D scalar volume. If a vector/RGB or 4D array
    # slips through, coerce to 3D grayscale rather than crashing the SimpleITK
    # filters (which reject >3D). The real routing fix lives in pipeline._find_demo_real_volume.
    vol = np.asarray(volume, dtype=np.float32)
    if vol.ndim == 4 and vol.shape[-1] in (3, 4):
        vol = vol[..., :3].mean(axis=-1)               # RGB(A) -> gray
    if vol.ndim != 3:
        log.warning("preprocess_ultrasound expected 3D, got shape %s — skipping denoise.",
                    vol.shape)
        return PreprocResult(volume=vol, method="none(unexpected-ndim)",
                             detail=f"Skipped US denoise: input ndim={vol.ndim}.", meta={})

    steps = []
    v = normalize_intensity(vol)
    steps.append("normalize(1-99pct->0-255)")

    used = "none"
    if method != "none":
        try:
            if method in ("auto", "gradient_anisotropic"):
                v = reduce_speckle_anisotropic(v, "gradient", iterations)
                used = "gradient_anisotropic_diffusion(SimpleITK)"
            elif method == "curvature_anisotropic":
                v = reduce_speckle_anisotropic(v, "curvature", iterations)
                used = "curvature_anisotropic_diffusion(SimpleITK)"
            elif method == "nlm":
                v = reduce_speckle_nlm(v)
                used = "nlm(OpenCV)"
            steps.append(used)
        except Exception as e:
            log.warning("Primary US denoiser '%s' failed (%s); trying NLM.", method, e)
            try:
                v = reduce_speckle_nlm(v)
                used = "nlm(OpenCV)[fallback]"
                steps.append(used)
            except Exception as e2:
                log.warning("NLM failed (%s); using median filter.", e2)
                v = _reduce_speckle_median(v)
                used = "median(scipy)[fallback]"
                steps.append(used)

    if use_clahe:
        try:
            v = apply_clahe(v)
            steps.append("clahe(per-slice)")
        except Exception as e:
            log.warning("CLAHE skipped (%s).", e)

    detail = "US preprocessing: " + " -> ".join(steps)
    log.info("%s", detail)
    return PreprocResult(volume=v.astype(np.float32), method=used, detail=detail,
                         meta={"steps": steps})
