#!/usr/bin/env python3
"""Iteration 5 — Build + freeze the REAL 2D beating-heart demo artifact.

Loads one real EchoNet 3d-echo cine (a 2D apical echo, 2D+time), runs the HONEST
cycle analysis, and freezes a self-contained, offline-ready artifact:

  demo/golden_echo/      heart.mp4, meta.json        (backend-side copy)
  frontend/golden_echo/  heart.mp4, curve.png, meta.json   (AR/echo page, offline L3)

NO fabricated 3D, NO LV contour, NO EF/FAC number (classical segmentation on raw
echo is unreliable — see app/echo_cycle.py). We ship the real beating cine + the
real motion/pulsation rhythm + ED/ES timing + honest narration.

    python scripts/build_echo_demo.py [path-to-echo.dcm]
Cite: EchoNet 3d-echo (https://github.com/echonet/3d-echo), per its license.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from app import ingestion, echo_cycle, narration

DEFAULT_DCM = os.path.join(ROOT, "data", "sample", "real", "echo", "A_0.dcm")
SRC_LABEL = "EchoNet 3d-echo (Person A, file A_0), apical view (US region 0)"
CITATION = ("EchoNet 3d-echo dataset, https://github.com/echonet/3d-echo "
            "(release v1.0). Used per the dataset's license; please cite the "
            "EchoNet authors.")
BACK_DIR = os.path.join(ROOT, "demo", "golden_echo")
FRONT_DIR = os.path.join(ROOT, "frontend", "golden_echo")


def write_mp4(frames: np.ndarray, ed: int, es: int, out_path: str, fps: float) -> None:
    """Encode the real cine as a browser-playable MP4 (OpenCV mp4v), upscaled,
    with a small honest label + ED/ES tag. The pixels are the REAL echo."""
    T, H, W = frames.shape
    scale = max(1.0, 480.0 / W)
    OW, OH = int(W * scale), int(H * scale)
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"),
                             max(fps, 6.0), (OW, OH))
    for i in range(T):
        g = np.clip(frames[i], 0, 255).astype(np.uint8)
        bgr = cv2.cvtColor(cv2.resize(g, (OW, OH)), cv2.COLOR_GRAY2BGR)
        cv2.rectangle(bgr, (0, 0), (OW, 22), (18, 22, 30), -1)
        cv2.putText(bgr, "REAL 2D ECHO - EchoNet 3d-echo (apical)", (8, 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (150, 200, 255), 1, cv2.LINE_AA)
        tag = "END-DIASTOLE" if i == ed else ("END-SYSTOLE" if i == es else "")
        if tag:
            cv2.putText(bgr, tag, (8, OH - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 230, 255), 2, cv2.LINE_AA)
        writer.write(bgr)
    writer.release()


def write_curve(analysis: dict, out_path: str) -> None:
    motion = analysis["cardiac_motion"]; dark = analysis["darkpool"]
    ed, es = analysis["ed_frame"], analysis["es_frame"]
    x = list(range(len(dark)))
    fig, ax = plt.subplots(figsize=(6.2, 2.6), dpi=100)
    ax.plot(x, dark, color="#5b9dff", lw=2, label="dark-pool pulsation (chamber-size proxy)")
    ax.plot(x, motion, color="#43c08a", lw=1.5, alpha=.8, label="cardiac motion (|Δframe|)")
    ax.axvline(ed, color="#43c08a", ls="--", lw=1.5); ax.text(ed, 1.02, "ED", color="#43c08a", ha="center")
    ax.axvline(es, color="#ec5b50", ls="--", lw=1.5); ax.text(es, 1.02, "ES", color="#ec5b50", ha="center")
    ax.set_xlabel("frame (cardiac cycle)"); ax.set_ylabel("normalized")
    ax.set_title("Real cardiac rhythm (uncalibrated proxies — not FAC/EF)", fontsize=10)
    ax.legend(fontsize=7, loc="lower right"); ax.set_ylim(-0.05, 1.12)
    fig.tight_layout(); fig.savefig(out_path); plt.close(fig)


def main() -> int:
    dcm = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DCM
    if not os.path.exists(dcm):
        print(f"ERROR: echo file not found: {dcm}\n"
              "Run scripts/inspect_echo.py (or pull one A_*.dcm) first.", file=sys.stderr)
        return 1
    os.makedirs(BACK_DIR, exist_ok=True); os.makedirs(FRONT_DIR, exist_ok=True)

    cine = ingestion.load_echo_cine(dcm, region_index=0)
    analysis = echo_cycle.analyze(cine.frames, fps=cine.fps, cm_per_px=cine.cm_per_px)

    # Honest narration (LLM if key, else templated).
    summary = {
        "anatomy_label": "a real 2D apical echocardiogram (beating heart)",
        "modality": "ultrasound (2D cine, 2D+time)",
        "confidence": analysis["confidence"],
        "echo": {"fps": analysis["fps"], "n_frames": analysis["n_frames"],
                 "ed_frame": analysis["ed_frame"], "es_frame": analysis["es_frame"],
                 "rel_darkpool_change_pct": analysis["rel_darkpool_change_pct"]},
        "measurements": analysis["measurements"],
        "caveat": analysis["caveat"],
    }
    narr = narration.narrate_echo(summary)

    # Artifacts
    write_mp4(cine.frames, analysis["ed_frame"], analysis["es_frame"],
              os.path.join(FRONT_DIR, "heart.mp4"), cine.fps)
    import shutil
    shutil.copyfile(os.path.join(FRONT_DIR, "heart.mp4"), os.path.join(BACK_DIR, "heart.mp4"))
    write_curve(analysis, os.path.join(FRONT_DIR, "curve.png"))

    meta = {
        "data_source": "REAL",
        "modality": "ultrasound (2D cine)",
        "source": SRC_LABEL,
        "citation": CITATION,
        "is_synthetic_placeholder": False,
        "two_d_plus_time": True,
        "anatomy_label": summary["anatomy_label"],
        "fps": analysis["fps"], "n_frames": analysis["n_frames"],
        "ed_frame": analysis["ed_frame"], "es_frame": analysis["es_frame"],
        "rel_darkpool_change_pct": analysis["rel_darkpool_change_pct"],
        "cardiac_motion": analysis["cardiac_motion"], "darkpool": analysis["darkpool"],
        "confidence": analysis["confidence"],
        "measurements": analysis["measurements"],
        "lv_segmentation_reliable": analysis["lv_segmentation_reliable"],
        "caveat": analysis["caveat"],
        "narration": narr["text"], "narration_mode": narr["mode"], "narration_model": narr["model"],
    }
    for d in (FRONT_DIR, BACK_DIR):
        with open(os.path.join(d, "meta.json"), "w") as f:
            json.dump(meta, f, indent=2)

    print("=== REAL beating-heart demo frozen ===")
    print("source        :", SRC_LABEL)
    print("frames / fps  :", analysis["n_frames"], "/", analysis["fps"])
    print("ED / ES frame :", analysis["ed_frame"], "/", analysis["es_frame"])
    print("rel dark-pool change (uncalibrated, NOT FAC/EF):",
          analysis["rel_darkpool_change_pct"], "%")
    print("confidence    :", analysis["confidence"]["overall"],
          analysis["confidence"]["overall_label"],
          "| low:", analysis["confidence"]["low_confidence_regions"])
    print(f"narration[{narr['mode']}]:", narr["text"])
    print("artifacts     :", FRONT_DIR, "+", BACK_DIR, "(heart.mp4, curve.png, meta.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
