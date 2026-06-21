#!/usr/bin/env python3
"""TASK 5 — Generate DEMO_RUNBOOK.md from the FROZEN golden artifact.

The runbook gives the team: the exact click sequence, a REAL-vs-FALLBACK table
(so nobody overclaims under questioning), pre-written HONEST answers to the
predictable hard questions, and data citations. Numbers come from the committed
golden artifact so they match what the judge will see.

    python scripts/generate_runbook.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATUS = os.path.join(ROOT, "demo", "golden", "status.json")
META = os.path.join(ROOT, "frontend", "golden", "golden_meta.json")
OUT = os.path.join(ROOT, "DEMO_RUNBOOK.md")


def load(p, default):
    try:
        return json.load(open(p))
    except Exception:
        return default


def main() -> int:
    st = load(STATUS, {})
    meta = load(META, {})
    if not st:
        print("WARN: no frozen status — run scripts/freeze_golden.py first.",
              file=sys.stderr)

    conf = (meta.get("confidence") or {})
    size = (meta.get("approx_size") or {})
    stages = st.get("stages", {})
    data_source = st.get("data_source", "SYNTHETIC_PLACEHOLDER")
    modality = st.get("modality", "ultrasound")

    def mode(stage):
        return (stages.get(stage, {}) or {}).get("mode", "?")

    md = f"""# DEMO RUNBOOK — SonoXR / EchoAR

_Auto-generated from the frozen golden artifact (`demo/golden/status.json`) so the
numbers below match what the judge sees. Re-run `python scripts/generate_runbook.py`
after `scripts/freeze_golden.py`._

## Locked demo subject
- **Data source:** `{data_source}`  ·  **modality:** `{modality}`
- **Subject:** {meta.get('anatomy_label', st.get('anatomy_label', 'n/a'))}
- **Reconstructed size:** ~{size.get('segmented_volume_cm3', '?')} cm³,
  bounding box {size.get('bounding_box_mm', '?')} mm
- **Confidence:** overall {conf.get('overall', '?')} ({conf.get('overall_label', '?')});
  low-confidence region(s): **{', '.join(conf.get('low_confidence_regions') or []) or 'none'}**
- **Live recompute latency:** < 1 s on CPU (see REPORT_4.md). If anything is slow
  or errors, `/demo` auto-serves the frozen cache (L2); the AR page loads its
  bundled copy (L3).

> ⚠️ This subject is a **clearly-labeled SYNTHETIC PLACEHOLDER** (not a real scan).
> To demo on a real volume, drop one in `data/sample/real/` (or set
> `DEMO_VOLUME_PATH`), then re-run `scripts/freeze_golden.py`. `/demo` will report
> `data_source: REAL`.

## Exact click sequence (≈60 seconds)
1. **Before the judges arrive:** `python scripts/freeze_golden.py` (freezes the
   artifact), then start the backend and the page:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   python -m http.server 5173
   ```
   Open `http://localhost:5173/frontend/ar.html` (or `http://<laptop-ip>:5173/...`
   on a phone, same Wi-Fi).
2. **The model is already on screen** (bundled artifact loads on page open — no
   blank state).
3. Press the big **▶ Run Demo** button → the reconstruction shows in <1 s and the
   layer badge reads **LIVE (L1)** (or **CACHED/OFFLINE** if the backend is down —
   the model still shows).
4. **Drag to orbit.** Point out: the recognizable 3D anatomy, the **confidence**
   chips, and the amber **"Re-scan recommended"** note on the low-confidence region.
5. Read the one-line **narration** caption aloud.
6. On a **phone**, tap **View in AR** → place the model in the room. That's the wow.
7. **If everything fails:** play `demo/backup_demo.mp4` (rendered backup clip).

## REAL vs FALLBACK — what is genuine AI/CV vs heuristic (don't overclaim)
`status.json` is the source of truth. Frozen golden run:

| Stage | This run | What it is |
|---|---|---|
| Ingestion | `{mode('ingestion')}` | SimpleITK volume read, real voxel spacing preserved |
| Preprocessing | `{mode('preprocessing')}` | ultrasound-aware denoise (anisotropic diffusion) + CLAHE; skipped for CT/MRI |
| Segmentation | `{mode('segmentation')}` | **classical CV** — 3D Otsu threshold + morphology + largest connected component (NOT a neural net) |
| Reconstruction | `{mode('reconstruction')}` | marching cubes on the real 3D mask (recognizable anatomy) |
| Meshing | `{mode('meshing')}` | trimesh Taubin smooth + quadric decimation → GLB |
| Narration | `{mode('narration')}` | **LLM** — Claude `claude-sonnet-4-6` (REAL_AI) when `ANTHROPIC_API_KEY` is set; otherwise a templated fallback that still states size + flags uncertainty |

**Where the AI is:** (1) the 3D reconstruction pipeline (computer vision), and
(2) the **uncertainty-aware narration** (LLM). The confidence proxy is a
transparent CV heuristic (boundary sharpness + component stability + threshold
ambiguity), not a learned/calibrated clinical metric — describe it as
**capture-quality / re-scan guidance**, not diagnosis.

**NOT built in this codebase (say so plainly if asked):** ejection fraction (EF),
CAMUS 2D-echo ingestion, a beating-heart / cardiac-cycle animation, and any
learned segmentation model (the U-Net hook is a stub). Don't imply otherwise.

## Predictable hard questions — honest answers
**"Doesn't Caption Health / EchoNet already do automated EF?"**
Yes — automated EF is established work. We do **not** compute EF in this build.
Our angle is different: **on-phone AR accessibility** of a 3D reconstruction plus
**calibrated, visible uncertainty**, built in 24 h on open data. EF is a natural
next step (it needs end-diastole + end-systole volumes, i.e. a 4D/time series).

**"Where exactly is the AI?"**
Two places: the 3D **reconstruction** (CV pipeline: thresholding → morphology →
marching cubes) and the **uncertainty-aware narration** (Claude `claude-sonnet-4-6`,
which names what's visible and flags low-confidence regions for re-scan).

**"Is the reconstruction / any number clinically validated?"**
No. Nothing here is a medical device. The demo subject is a **labeled synthetic
phantom**; we also validated the pipeline on real **CT / MRI / microscopy** volumes
(not ultrasound) — see REPORT.md. We present it as a **demo**, not a diagnostic.

**"What's real vs faked here?"**
Nothing is faked — `status.json` records `PRIMARY` / `FALLBACK` / `REAL_AI` for
every stage (shown above), and all synthetic data is labeled `SYNTHETIC
PLACEHOLDER` in the DICOM tags, the manifest, `/status`, `/demo`, and the
narration text. We can show the JSON live.

**"Why does the demo say SYNTHETIC?"**
Because programmatic, license-clean access to a real 3D fetal/echo ultrasound is
restricted; rather than fake one, we ship a clearly-labeled phantom and a
one-command path to drop in a real volume.

## Data citations
- **Demo subject:** synthetic anatomical phantom generated by
  `scripts/download_sample_data.py` (ours; labeled SYNTHETIC PLACEHOLDER).
- **Pipeline validation volumes:** scikit-image sample data — `brain` (MRI) and
  `cells3d` (confocal) — and the **Stanford volume data archive** (CThead CT,
  `graphics.stanford.edu/data/voldata`). Cite per each source's terms.
- **CAMUS / 3D echo:** **not used** in this build (no CAMUS data is bundled or
  cited, because none is used).
- **Narration model:** Anthropic Claude `claude-sonnet-4-6` via the official SDK.

## Pre-flight checklist
- [ ] `python scripts/freeze_golden.py` (latency < 1 s; artifact frozen)
- [ ] `export ANTHROPIC_API_KEY=...` then `python scripts/smoke_test_narration.py`
      → expect `mode: REAL_AI`, exit 0 (skip if demoing the templated fallback)
- [ ] `python scripts/record_demo.py` → `demo/backup_demo.mp4` exists
- [ ] backend up (`:8000`), page served (`:5173`), opened on the phone over LAN
- [ ] verified **View in AR** works on the actual phone
"""
    # --- Real 2D echo demo section (iteration 5), if the artifact exists -------
    echo_meta = os.path.join(ROOT, "frontend", "golden_echo", "meta.json")
    em = load(echo_meta, {})
    if em:
        ec = em.get("confidence", {})
        md += f"""

---

# REAL 2D ECHO DEMO (EchoNet 3d-echo) — separate page

A second, fully-offline demo on **real public data**: `frontend/echo.html` plays a
real 2D echocardiogram cine (a beating heart).

- **Source:** {em.get('source')}
- **Citation:** {em.get('citation')}
- **What it is:** real **2D + time** ultrasound cine ({em.get('n_frames')} frames @
  {em.get('fps')} fps). The EchoNet `dataset.zip` (v1.0) is 2D cine loops, **not** 3D
  volumes (verified from the DICOM tags: SOP = US Multi-frame, frame axis = time).
- **What's REAL:** the beating-heart cine, the cardiac-motion + dark-pool **rhythm**
  signals, and approximate **ED/ES timing** (ED frame {em.get('ed_frame')}, ES frame
  {em.get('es_frame')}).
- **What we do NOT claim:** an LV trace, fractional-area-change, or **ejection
  fraction**. Classical thresholding on raw echo did **not** reliably trace the LV
  (it under/over-segments), so — per our no-faking rule — we report none. A clinical
  border needs a trained segmentation model (CAMUS/EchoNet use U-Nets) and EF needs
  3D/biplane volumes. `lv_segmentation_reliable={em.get('lv_segmentation_reliable')}`.
- **Capture confidence (real, echo-physics):** overall {ec.get('overall')}
  ({ec.get('overall_label')}); harder regions: {', '.join(ec.get('low_confidence_regions') or []) or 'none'}.
- **Narration ({em.get('narration_mode')}):** {em.get('narration')}
- **To run:** `python scripts/build_echo_demo.py` then serve the repo and open
  `frontend/echo.html` (no backend needed — it loads the bundled `golden_echo/`).

**Echo Q&A — "is this EF / clinically validated?"** No. We show real motion and
rhythm only; EF/area are not measured here and nothing is a medical device.
"""

    # --- Real 3D LV (CAMUS Simpson's biplane) section (iteration 6) -----------
    cam_meta = os.path.join(ROOT, "frontend", "golden_camus", "meta.json")
    cm = load(cam_meta, {})
    if cm:
        md += f"""

---

# REAL 3D LV + EF (CAMUS, Simpson's biplane) — the hero demo

A **beating 3D left ventricle with ejection fraction**, reconstructed from **real
expert-annotated** data: `frontend/camus.html` (offline; loads `golden_camus/`).

- **Patient / quality:** {cm.get('patient')} · image quality {cm.get('image_quality')}
- **EDV / ESV / EF:** {cm.get('EDV_mL')} mL / {cm.get('ESV_mL')} mL / **{cm.get('EF_pct')}%**
- **CAMUS reference EF:** {cm.get('reference_ef')}% (ours − ref = {cm.get('ef_vs_reference_pp')} pp;
  both normal — ours is a geometric biplane estimate, the reference is CAMUS's own).
- **Method (say it exactly):** {cm.get('method')}
- **What's REAL:** the LV cavity contours are **expert annotations**; the 3D shape is
  the **standard clinical** Simpson's biplane method of discs; EDV/ESV/EF use the
  **clinical biplane formula** `V=(π/4)·Σ D₄·D₂·h`. The beating is an ED↔ES morph of
  the two reconstructed phases.
- **What we do NOT claim:** a volumetric 3D-echo acquisition (this is biplane geometry
  from 2D views), or clinical-grade accuracy (apical foreshortening + the
  elliptical-disc assumption are the known limitations). Not a medical device.
- **Narration ({cm.get('narration_mode')}):** {cm.get('narration')}
- **Citation (REQUIRED):** {cm.get('citation')}
- **To run:** `python scripts/build_camus_demo.py` then open `frontend/camus.html`.

**Q&A — "is the EF clinically validated?"** No — it's the standard Simpson's biplane
method computed on real expert masks; it lands in the normal range and within ~10 pp
of CAMUS's own reference EF. Framed as a faithful demo of the clinical method, not a
diagnosis.
"""

    with open(OUT, "w") as f:
        f.write(md)
    print(f"Wrote {OUT} ({len(md)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
