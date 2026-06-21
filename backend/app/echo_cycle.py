"""Iteration 5 — Honest cardiac-cycle analysis of a real 2D echo cine.

IMPORTANT / HONESTY: a clinically meaningful LV endocardial border (and therefore
ejection fraction, or even a 2D fractional-area-change) requires a TRAINED
segmentation model — that is exactly what CAMUS/EchoNet use. We attempted
classical intensity thresholding on the raw B-mode pixels and it does NOT reliably
trace the LV (it oscillates between bright speckle and the whole dark sector). So
this module deliberately does NOT output an LV contour or an EF/FAC number.

What it DOES output is honest and defensible from real pixels:
  * cardiac_motion[]  — per-frame frame-to-frame change inside the fan. This
                        genuinely pulses with the heartbeat (the cine is real).
  * darkpool[]        — per-frame relative dark-pool fraction (a chamber-size
                        PROXY), normalized + uncalibrated. Pulses with the cycle.
  * ed_frame / es_frame — approximate end-diastole / end-systole TIMING from the
                        smoothed dark-pool curve (largest/smallest cavity). Timing
                        only — NOT a volume or area measurement.
  * per-region capture-confidence — honest echo-physics signal: the near-field
                        (apical clutter) and far-field (lateral/basal dropout) are
                        genuinely less reliable than mid-depth. Feeds the narration.

Everything is CPU-only and label-honest.
"""

from __future__ import annotations

import logging

import numpy as np
from scipy import ndimage as ndi

log = logging.getLogger("sonoxr.echo_cycle")


def _fan_mask(mean_frame: np.ndarray) -> np.ndarray:
    """The ultrasound sector = where there is signal (outside the fan is ~black)."""
    m = mean_frame > 8
    m = ndi.binary_closing(m, iterations=3)
    m = ndi.binary_fill_holes(m)
    return m


def _norm(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, float)
    lo, hi = x.min(), x.max()
    return (x - lo) / (hi - lo) if hi - lo > 1e-9 else np.zeros_like(x)


def analyze(frames: np.ndarray, fps: float = 15.0, cm_per_px: float = 0.0) -> dict:
    """Run the honest cycle analysis on (T,H,W) grayscale cine frames."""
    f = frames.astype(np.float32)
    T = f.shape[0]
    fan = _fan_mask(f.mean(0))
    fan_area = max(int(fan.sum()), 1)

    # --- cardiac motion: mean |Δframe| inside the fan (real rhythm signal) ----
    motion = np.zeros(T)
    for i in range(1, T):
        d = np.abs(f[i] - f[i - 1])
        motion[i] = d[fan].mean()
    motion[0] = motion[1] if T > 1 else 0.0

    # --- dark-pool proxy: fraction of fan that is "blood-pool dark" -----------
    dark_t = float(np.percentile(f[:, fan], 30))   # blood-pool ≈ darkest third in-fan
    darkpool = np.array([float(((f[i] < dark_t) & fan).sum()) / fan_area for i in range(T)])
    dp_s = ndi.uniform_filter1d(darkpool, size=3, mode="nearest")

    ed_frame = int(dp_s.argmax())          # largest cavity ≈ end-diastole
    es_frame = int(dp_s.argmin())          # smallest cavity ≈ end-systole
    # Uncalibrated relative change in the dark-pool proxy (NOT FAC, NOT EF).
    rel_change = float(100.0 * (dp_s.max() - dp_s.min()) / max(dp_s.max(), 1e-6))

    # --- honest per-region capture confidence (echo physics) ------------------
    confidence = _capture_confidence(f, fan)

    log.info("Echo cycle: T=%d fps=%.1f ED=%d ES=%d rel_dark_change=%.0f%% lowconf=%s",
             T, fps, ed_frame, es_frame, rel_change, confidence["low_confidence_regions"])

    return {
        "n_frames": T,
        "fps": round(float(fps), 2),
        "cardiac_motion": _norm(motion).round(3).tolist(),
        "darkpool": _norm(darkpool).round(3).tolist(),
        "ed_frame": ed_frame,
        "es_frame": es_frame,
        "rel_darkpool_change_pct": round(rel_change, 0),
        "confidence": confidence,
        # LOUD honesty flags (consumed by narration + UI + report):
        "lv_segmentation_reliable": False,
        "measurements": {
            "ejection_fraction": None,        # NOT computed — needs ED+ES volumes (3D/biplane) + a trained border
            "fractional_area_change": None,   # NOT computed — classical LV border is unreliable on raw echo
        },
        "caveat": ("Real 2D echo cine. Cardiac MOTION and dark-pool PULSATION are "
                   "measured from real pixels; ED/ES are approximate TIMING. We do "
                   "NOT report an LV trace, FAC, or EF — a clinical border needs a "
                   "trained segmentation model (e.g. the U-Nets CAMUS/EchoNet use)."),
    }


def _capture_confidence(f: np.ndarray, fan: np.ndarray) -> dict:
    """Per-depth capture quality from boundary sharpness — honest echo signal.

    In an apical view the transducer/apex is at the TOP (near-field): bright
    reverberation clutter; the base/valves are at the BOTTOM (far-field):
    attenuation + dropout. Mid-depth is usually the cleanest. We score the three
    depth bands by mean edge strength and flag the weak ones."""
    mean = f.mean(0)
    grad = ndi.gaussian_gradient_magnitude(mean, sigma=1.0)
    ys = np.where(fan.any(axis=1))[0]
    if ys.size == 0:
        return {"overall": 0.0, "overall_label": "low", "per_region": [],
                "low_confidence_regions": ["whole image"]}
    y0, y1 = ys.min(), ys.max()
    edges = np.linspace(y0, y1 + 1, 4)
    names = ["apical (near-field)", "mid-ventricle", "basal (far-field)"]
    raw = []
    for i in range(3):
        band = np.zeros_like(fan)
        band[int(edges[i]):int(edges[i + 1])] = True
        sel = fan & band
        raw.append(float(grad[sel].mean()) if sel.any() else 0.0)
    raw = np.array(raw)
    norm = _norm(raw) if raw.max() - raw.min() > 1e-9 else np.full(3, 0.6)
    # map to 0..1 confidence, keep it from hitting exactly 0/1
    conf = np.clip(0.35 + 0.5 * norm, 0, 1)
    per_region, low = [], []
    for nm, c in zip(names, conf):
        lab = "high" if c >= 0.7 else ("medium" if c >= 0.55 else "low")
        per_region.append({"region": nm, "confidence": round(float(c), 3), "label": lab})
        if lab == "low":
            low.append(nm)
    overall = float(conf.mean())
    return {
        "overall": round(overall, 3),
        "overall_label": "high" if overall >= 0.7 else ("medium" if overall >= 0.55 else "low"),
        "per_region": per_region,
        "low_confidence_regions": low,
        "method": "per-depth boundary sharpness (apical clutter / far-field dropout)",
    }
