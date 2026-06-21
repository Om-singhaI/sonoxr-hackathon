# DEMO RUNBOOK — SonoXR / EchoAR

_Auto-generated from the frozen golden artifact (`demo/golden/status.json`) so the
numbers below match what the judge sees. Re-run `python scripts/generate_runbook.py`
after `scripts/freeze_golden.py`._

## Locked demo subject
- **Data source:** `SYNTHETIC_PLACEHOLDER`  ·  **modality:** `ultrasound`
- **Subject:** a SYNTHETIC PLACEHOLDER phantom (organ-like model, NOT a real scan)
- **Reconstructed size:** ~29.56 cm³,
  bounding box [38.77, 37.25, 40.47] mm
- **Confidence:** overall 0.757 (high);
  low-confidence region(s): **lower portion**
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
| Ingestion | `PRIMARY` | SimpleITK volume read, real voxel spacing preserved |
| Preprocessing | `gradient_anisotropic_diffusion(SimpleITK)` | ultrasound-aware denoise (anisotropic diffusion) + CLAHE; skipped for CT/MRI |
| Segmentation | `PRIMARY` | **classical CV** — 3D Otsu threshold + morphology + largest connected component (NOT a neural net) |
| Reconstruction | `PRIMARY` | marching cubes on the real 3D mask (recognizable anatomy) |
| Meshing | `PRIMARY (no decimation)` | trimesh Taubin smooth + quadric decimation → GLB |
| Narration | `FALLBACK` | **LLM** — Claude `claude-sonnet-4-6` (REAL_AI) when `ANTHROPIC_API_KEY` is set; otherwise a templated fallback that still states size + flags uncertainty |

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


---

# REAL 2D ECHO DEMO (EchoNet 3d-echo) — separate page

A second, fully-offline demo on **real public data**: `frontend/echo.html` plays a
real 2D echocardiogram cine (a beating heart).

- **Source:** EchoNet 3d-echo (Person A, file A_0), apical view (US region 0)
- **Citation:** EchoNet 3d-echo dataset, https://github.com/echonet/3d-echo (release v1.0). Used per the dataset's license; please cite the EchoNet authors.
- **What it is:** real **2D + time** ultrasound cine (18 frames @
  6.21 fps). The EchoNet `dataset.zip` (v1.0) is 2D cine loops, **not** 3D
  volumes (verified from the DICOM tags: SOP = US Multi-frame, frame axis = time).
- **What's REAL:** the beating-heart cine, the cardiac-motion + dark-pool **rhythm**
  signals, and approximate **ED/ES timing** (ED frame 10, ES frame
  2).
- **What we do NOT claim:** an LV trace, fractional-area-change, or **ejection
  fraction**. Classical thresholding on raw echo did **not** reliably trace the LV
  (it under/over-segments), so — per our no-faking rule — we report none. A clinical
  border needs a trained segmentation model (CAMUS/EchoNet use U-Nets) and EF needs
  3D/biplane volumes. `lv_segmentation_reliable=False`.
- **Capture confidence (real, echo-physics):** overall 0.523
  (low); harder regions: mid-ventricle, basal (far-field).
- **Narration (FALLBACK):** This is a real 2D ultrasound of a beating heart — an apical view showing the cardiac chambers, captured live across the cardiac cycle. The mid-ventricle, basal (far-field) were harder to see clearly, which is common in echo — that region would benefit from a better acoustic window. We show the real motion and rhythm; we deliberately do not report an ejection fraction or exact chamber size here — those need a trained segmentation model, not raw pixel thresholds.
- **To run:** `python scripts/build_echo_demo.py` then serve the repo and open
  `frontend/echo.html` (no backend needed — it loads the bundled `golden_echo/`).

**Echo Q&A — "is this EF / clinically validated?"** No. We show real motion and
rhythm only; EF/area are not measured here and nothing is a medical device.


---

# REAL 3D LV + EF (CAMUS, Simpson's biplane) — the hero demo

A **beating 3D left ventricle with ejection fraction**, reconstructed from **real
expert-annotated** data: `frontend/camus.html` (offline; loads `golden_camus/`).

- **Patient / quality:** patient0001 · image quality Good
- **EDV / ESV / EF:** 91.0 mL / 32.7 mL / **64.0%**
- **CAMUS reference EF:** 54.0% (ours − ref = 10.0 pp;
  both normal — ours is a geometric biplane estimate, the reference is CAMUS's own).
- **Method (say it exactly):** 3D LV reconstructed from CAMUS 2D apical views (2CH+4CH) via Simpson's biplane method of discs; EF by the clinical biplane formula. NOT a 3D-echo volume acquisition.
- **What's REAL:** the LV cavity contours are **expert annotations**; the 3D shape is
  the **standard clinical** Simpson's biplane method of discs; EDV/ESV/EF use the
  **clinical biplane formula** `V=(π/4)·Σ D₄·D₂·h`. The beating is an ED↔ES morph of
  the two reconstructed phases.
- **What we do NOT claim:** a volumetric 3D-echo acquisition (this is biplane geometry
  from 2D views), or clinical-grade accuracy (apical foreshortening + the
  elliptical-disc assumption are the known limitations). Not a medical device.
- **Narration (FALLBACK):** This is the heart's left ventricle, shown beating between its fullest point (end-diastole) and its emptiest (end-systole). It holds about 91.0 mL when full and 32.7 mL after the beat, so it pumps out roughly 64.0% each cycle — the ejection fraction. This 3D shape was reconstructed from real expert-traced 2D apical views using Simpson's biplane method of discs — the clinical standard — not a 3D-echo volume scan.
- **Citation (REQUIRED):** CAMUS dataset — S. Leclerc et al., 'Deep Learning for Segmentation using an Open Large-Scale Dataset in 2D Echocardiography', IEEE TMI 38(9):2198-2210, 2019. doi:10.1109/TMI.2019.2900516
- **To run:** `python scripts/build_camus_demo.py` then open `frontend/camus.html`.

**Q&A — "is the EF clinically validated?"** No — it's the standard Simpson's biplane
method computed on real expert masks; it lands in the normal range and within ~10 pp
of CAMUS's own reference EF. Framed as a faithful demo of the clinical method, not a
diagnosis.
