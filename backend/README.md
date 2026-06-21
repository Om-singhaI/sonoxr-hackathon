# SonoXR / EchoAR — backend

Turns a **volumetric ultrasound** (3D/4D DICOM) into a mobile-AR-ready **`.glb`**
mesh plus **plain-language, uncertainty-aware narration**. FastAPI service; the
Unity / WebXR frontend is separate (it uploads data, polls status, downloads the
`.glb` + narration JSON).

---

## The one principle that matters

There are **two separate reliability goals**, kept strictly apart:

- **Golden demo path** — one curated, pre-verified input (`POST /demo`) that runs
  the full pipeline and produces **recognizable anatomy every time**. This is
  what we show judges. It must never fail.
- **Service robustness** — the service must **never crash** on arbitrary input.
  Every stage degrades gracefully and always returns *something*.

Robustness fallbacks **do not contaminate** the golden path. The golden path runs
on known-good data and looks great; the fallbacks only exist so live uploads of
unknown data don't crash the demo.

### Why a VOLUME, not a 2D sweep

The naive approach (stack freehand 2D frames along a fabricated depth axis →
marching cubes) makes an **unrecognizable blob**, because 2D frames have no real
spatial registration. So the **primary path ingests a real volumetric ultrasound**
where the depth axis is real, segments in 3D, and runs marching cubes on the
actual volume → recognizable anatomy. The 2D-sweep path (and the UltrasODM
research model) are **stretch/robustness only** — wired behind the same interface
with timeouts + try/except, and the demo never depends on them.

---

## Pipeline

```
1. Ingestion      DICOM volume / series / NIfTI [PRIMARY]   |  video / frames zip [FALLBACK]
2. Segmentation   3D Otsu + morphology + largest CC          |  per-frame 2D Otsu
                  + per-region CONFIDENCE proxy
3. Reconstruction marching cubes on the real 3D mask         |  uniform voxel-stack (low fidelity)
                  (UltrasODM + Poisson = stretch, assumed off)
4. Meshing        trimesh: Taubin smooth -> quadric decimate (~30–80k tris) -> GLB
5. Narration      Claude (claude-sonnet-4-6): warm AR commentary that FLAGS low-confidence regions
                  (templated fallback if the API is unavailable)
6. Serving        trigger / poll / download endpoints + one-button /demo
```

---

## Setup

```bash
# from the repo root
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Narration key (optional but needed for REAL_AI narration)
cp .env.example .env                 # then edit .env and paste your ANTHROPIC_API_KEY
export ANTHROPIC_API_KEY=sk-ant-...  # or rely on .env (loaded via python-dotenv)

# Fetch a real volume OR generate the clearly-labeled synthetic placeholder.
# (Prints instructions for getting a real scan; always leaves a runnable sample.)
python scripts/download_sample_data.py
```

> **Dependency notes.** The PRIMARY pipeline needs only numpy / scipy /
> scikit-image / trimesh / SimpleITK / pydicom. `SimpleITK` is the preferred
> DICOM reader; if its wheel is unavailable on your Python, the code **falls back
> to pydicom automatically**. `fast-simplification` backs decimation; without it
> the mesh still exports (just heavier) and the status says so. `open3d` is only
> for the UltrasODM stretch path and is commented out by default.

### Run

```bash
uvicorn app.main:app --reload
# -> http://127.0.0.1:8000   (interactive docs at /docs)
```

---

## The 30-second demo

```bash
curl -s -X POST http://127.0.0.1:8000/demo | python3 -m json.tool
```

Returns the per-stage modes, the narration, and a `model_url`. Then:

```bash
# download the recognizable .glb (open in any glTF viewer / drop into Unity/WebXR)
curl -s http://127.0.0.1:8000/model/<job_id> -o demo.glb
```

`POST /demo` loads the bundled, pre-verified sample and runs the whole pipeline
**synchronously**, so it returns a ready result. It's the one-button judging path.

---

## Endpoints — `curl` for every one

```bash
BASE=http://127.0.0.1:8000

# Health + banner
curl -s $BASE/health
curl -s $BASE/

# Golden path (synchronous): full pipeline on the bundled sample
curl -s -X POST $BASE/demo | python3 -m json.tool

# Upload an input -> {job_id, input_type, is_volume_primary_path}
#   accepts: a .dcm, a zip of a DICOM series, a .nii/.nii.gz, an .mp4, or a zip of frames
curl -s -X POST $BASE/upload -F "file=@/path/to/volume.dcm" | python3 -m json.tool

# Kick off processing in the BACKGROUND (stages 2-5), then poll
curl -s -X POST $BASE/process/<job_id>
curl -s $BASE/status/<job_id> | python3 -m json.tool

# Download the reconstructed mesh
curl -s $BASE/model/<job_id> -o model.glb

# (Re)generate narration JSON for a processed job
curl -s -X POST $BASE/narrate/<job_id> | python3 -m json.tool
```

`GET /status/{job_id}` reports, for **each stage**, whether it ran `PRIMARY` or
`FALLBACK` (narration reports `REAL_AI` or `FALLBACK`) — handy for Q&A:

```json
{
  "status": "done",
  "current_stage": "done",
  "is_synthetic_placeholder": true,
  "stages": {
    "ingestion":      {"status": "done", "mode": "PRIMARY",  "detail": "DICOM series (96 slices) via SimpleITK."},
    "segmentation":   {"status": "done", "mode": "PRIMARY",  "detail": "Otsu 3D threshold + morphology + largest of N components."},
    "reconstruction": {"status": "done", "mode": "PRIMARY",  "detail": "Marching cubes on real volume mask ..."},
    "meshing":        {"status": "done", "mode": "PRIMARY",  "detail": "GLB exported ...; smoothed; decimated."},
    "narration":      {"status": "done", "mode": "REAL_AI",  "detail": "Generated by claude-sonnet-4-6."}
  }
}
```

---

## REAL AI vs FALLBACK — per stage (for judging Q&A)

| Stage | **REAL / PRIMARY** (golden path) | **FALLBACK** (robustness) | What triggers the fallback |
|---|---|---|---|
| **1. Ingestion** | Volumetric DICOM/series/NIfTI read with **SimpleITK**, real voxel spacing preserved | **pydicom** reader; or 2D **OpenCV** frame extraction for video/zip | SimpleITK wheel missing → pydicom; a video/frames upload → 2D path |
| **2. Segmentation** | **3D** Otsu + 3D morphology + largest connected component on the real volume | Per-frame **2D** Otsu + morphology (unregistered) | Input was 2D (video/frames). *Pretrained U-Net is a stubbed upgrade — see below* |
| **3. Reconstruction** | **Marching cubes on the real 3D mask** with real spacing → recognizable anatomy | Uniform-spacing **voxel stack** → marching cubes (**low fidelity, fabricated depth**) | 2D input. UltrasODM stretch path is attempted first but assumed to fail |
| **4. Meshing** | trimesh Taubin smooth → **quadric decimation** (~30–80k tris) → GLB | GLB exported **without decimation** (still valid, just heavier) | `fast-simplification` not installed |
| **5. Narration** | **Claude `claude-sonnet-4-6`** — warm AR commentary that explicitly flags low-confidence regions | **Templated**, non-LLM narration (still honest about size + low-confidence + synthetic) | `ANTHROPIC_API_KEY` unset, SDK missing, API error, or a safety refusal |

The **honest-uncertainty** behavior is a required feature: stage 2 computes a
per-region confidence proxy (boundary sharpness + component stability + threshold
ambiguity), and stage 5 turns low-confidence regions into a spoken
*"this area was harder to capture clearly — a re-scan would give a sharper view."*

---

## Sample data — verify, don't assume

`scripts/download_sample_data.py`:

1. **Uses a real scan if you provide one** — drop a `.nii/.nii.gz`, a multi-frame
   `.dcm`, or a folder of DICOM slices into `data/sample/real/` and re-run.
2. Otherwise prints **clear instructions** on where to obtain a real 3D
   ultrasound (TCIA / Zenodo fetal-US, CETUS 3D echo, etc.) — it does **not**
   silently substitute a blob.
3. As a **last resort**, generates a **clearly-labeled SYNTHETIC PLACEHOLDER**
   phantom (a DICOM series, so the real primary path is exercised) so the
   pipeline is always testable.

> ⚠️ **The placeholder is marked `SYNTHETIC PLACEHOLDER` everywhere** — in the
> DICOM tags, a `SYNTHETIC_PLACEHOLDER.txt` sidecar, the `sample_manifest.json`
> (`is_synthetic_placeholder: true`), the `/status` + `/demo` responses, and the
> narration itself. **Replace `data/sample` with a real scan before the judged
> demo** so a placeholder never masquerades as a real reconstruction.

---

## What's stubbed / flagged LOUD (fill these in to upgrade)

These are intentional, clearly-marked stubs — the demo does **not** depend on any
of them, and they all fail safe to the paths above:

- **Pretrained ultrasound segmentation model** (nnU-Net / U-Net) —
  `segmentation.try_load_segmentation_model()` returns `None` (no bundled
  weights). Drop a checkpoint in `app/models/` and implement loading to upgrade
  stage 2. Until then, the Otsu threshold path runs.
- **UltrasODM 2D-sweep reconstruction** — `reconstruction.try_ultrasodm()` shells
  out to a wrapper in a subprocess with a hard 60s timeout and full try/except.
  It's disabled unless `ULTRASODM_RUNNER` points at a wrapper script; expect
  Mamba/conda + checkpoint breakage. Falls back silently.
- **Open3D Poisson surface** — `reconstruction.poisson_from_pointcloud()` only
  runs if UltrasODM yielded a point cloud *and* `open3d` is installed (commented
  out in `requirements.txt` by default).

---

## Layout

```
app/
  main.py            FastAPI app + endpoints (CORS open for the demo)
  ingestion.py       type detection + DICOM/NIfTI volume load (SimpleITK->pydicom) + video/frames
  segmentation.py    3D Otsu + morphology + largest CC + confidence proxy; 2D fallback
  reconstruction.py  marching cubes (volume); voxel-stack fallback; UltrasODM/Poisson stretch
  meshing.py         trimesh smooth + quadric decimate + GLB export
  narration.py       Claude narration (claude-sonnet-4-6) + templated fallback
  pipeline.py        orchestration, per-stage PRIMARY/FALLBACK status writes, demo prep
scripts/
  download_sample_data.py   real-scan-or-labeled-phantom sample fetcher
requirements.txt
.env.example
data/                jobs/<id>/ artifacts + sample/ (git-ignored)
```

Everything runs on **CPU** (no GPU assumed).

---

## Real data: EchoNet 3d-echo (iteration 5)

A real 2D echocardiography demo is available at `frontend/echo.html` (see
`frontend/README.md`). Data: **EchoNet 3d-echo** — https://github.com/echonet/3d-echo
(release v1.0). Used per the dataset's license; please cite the EchoNet authors.
Note: the released files are **2D cine (2D + time)**, not 3D volumes — we play them
faithfully rather than fabricate a 3D reconstruction. See `REPORT_5.md`.

---

## Real 3D LV + ejection fraction: CAMUS (iteration 6)

`frontend/camus.html` shows a **beating 3D left ventricle with EF**, reconstructed
from the **CAMUS** dataset's expert 2D apical masks (2CH+4CH, ED+ES) via **Simpson's
biplane method of discs** — the clinical standard, **not** a 3D-echo volume scan.
Build with `python scripts/build_camus_demo.py`. **Required citation:** S. Leclerc
et al., "Deep Learning for Segmentation using an Open Large-Scale Dataset in 2D
Echocardiography," IEEE TMI 38(9):2198-2210, 2019. doi:10.1109/TMI.2019.2900516.
EF is the standard biplane geometric estimate on real expert masks (not a clinical
device). See `REPORT_6.md`.
