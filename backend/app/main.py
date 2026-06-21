"""Stage 6 — FastAPI service (trigger / poll / download) + the golden /demo.

Endpoints
---------
  GET  /                  service banner + endpoint list
  GET  /health            liveness probe
  POST /upload            accept a DICOM/zip/mp4/frames file -> {job_id, input_type}
  POST /process/{job_id}  run stages 2-5 in the BACKGROUND, return immediately
  POST /demo              GOLDEN PATH: run the bundled sample end-to-end (sync)
  GET  /status/{job_id}   current stage + PRIMARY/FALLBACK per stage
  GET  /model/{job_id}    download the .glb
  POST /narrate/{job_id}  (re)generate narration JSON for a processed job

CORS is wide open — this is a demo service, not production.
"""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from fastapi import (BackgroundTasks, FastAPI, File, Form, HTTPException,
                     UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import ingestion, narration, pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("sonoxr.main")

# --- Frozen golden artifact (TASK 1/2): committed fallback for /demo ----------
GOLDEN_DIR = os.path.join(pipeline.BASE_DIR, "demo", "golden")
GOLDEN_GLB = os.path.join(GOLDEN_DIR, "model.glb")
GOLDEN_NARR = os.path.join(GOLDEN_DIR, "narration.json")
GOLDEN_STATUS = os.path.join(GOLDEN_DIR, "status.json")

# Hard ceiling on the live /demo recompute before we fall back to the cache (L2).
DEMO_TIMEOUT = float(os.environ.get("DEMO_TIMEOUT", "10"))
# Persistent pool so a timed-out live run keeps finishing in the background
# (harmless) without blocking the request or leaking a new executor each call.
_DEMO_EXECUTOR = ThreadPoolExecutor(max_workers=2)

app = FastAPI(
    title="SonoXR / EchoAR backend",
    version="0.1.0",
    description="Volumetric ultrasound -> AR-ready .glb + uncertainty-aware narration.",
)

# Permissive CORS for the demo (Unity / WebXR frontends hit this from anywhere).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Meta
# =============================================================================
@app.get("/")
def root():
    return {
        "service": "SonoXR / EchoAR backend",
        "primary_path": "volumetric DICOM -> 3D segmentation -> marching cubes -> .glb",
        "one_button_demo": "POST /demo",
        "endpoints": [
            "GET  /health",
            "POST /upload (multipart file)",
            "POST /process/{job_id}",
            "POST /demo",
            "GET  /status/{job_id}",
            "GET  /model/{job_id}",
            "POST /narrate/{job_id}",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


# =============================================================================
# Ingestion
# =============================================================================
@app.post("/upload")
async def upload(file: UploadFile = File(...), modality: str = Form("auto")):
    """Save an uploaded file, detect its type, and register a job.

    Accepts a DICOM .dcm, a zip of a DICOM series, a NIfTI volume, an MP4, or a
    zip of image frames. Volume types drive the PRIMARY path; video/frames drive
    the 2D robustness fallback.

    `modality` (form field): "auto" (default — detect from the DICOM tag),
    "ultrasound" (force the US-aware preprocessing path; use this for a converted
    3D-echo NIfTI, which carries no modality tag), or "ct_mri".
    """
    modality = modality if modality in ("auto", "ultrasound", "ct_mri") else "auto"
    job_id = pipeline.create_job(modality=modality)
    filename = os.path.basename(file.filename or "upload.bin")
    dest = os.path.join(pipeline.job_dir(job_id), filename)

    # Stream to disk in chunks so large volumes don't blow up memory.
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    input_type = ingestion.detect_input_type(filename, dest)
    status = pipeline.read_status(job_id)
    status["input_type"] = input_type
    status["source_path"] = dest
    pipeline.write_status(status)

    log.info("Upload %s -> job %s (type=%s, modality=%s, %d bytes)",
             filename, job_id, input_type, modality, os.path.getsize(dest))
    return {
        "job_id": job_id,
        "input_type": input_type,
        "modality": modality,
        "is_volume_primary_path": ingestion.is_volume_type(input_type),
        "next": f"POST /process/{job_id}",
    }


# =============================================================================
# Processing
# =============================================================================
@app.post("/process/{job_id}")
def process(job_id: str, background_tasks: BackgroundTasks):
    """Kick off stages 2-5 as a background task; poll /status for progress."""
    status = pipeline.read_status(job_id)
    if status is None:
        raise HTTPException(404, f"Unknown job {job_id}")
    if not status.get("source_path"):
        raise HTTPException(400, "Job has no uploaded input; call /upload first.")
    background_tasks.add_task(pipeline.run_pipeline, job_id)
    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "processing_started",
                 "poll": f"GET /status/{job_id}"},
    )


@app.post("/demo")
def demo():
    """THE GOLDEN PATH — one-button judging endpoint, with a triple-layer fallback
    so a judge ALWAYS sees a result (TASK 2):

      L1 LIVE   — recompute from the locked demo subject now (hard timeout).
      L2 CACHED — if live errors or exceeds DEMO_TIMEOUT, serve the committed
                  frozen golden artifact (demo/golden/).
      L3 STATIC — handled by the AR page: if THIS server is unreachable, the page
                  loads its bundled local copy (frontend/golden/). No backend.

    The chosen layer is reported in the response as `demo_layer`.
    """
    # ---- L1 LIVE (bounded by DEMO_TIMEOUT) ----------------------------------
    l1_error = None
    try:
        job_id = pipeline.prepare_demo_job()
        fut = _DEMO_EXECUTOR.submit(pipeline.run_pipeline, job_id)
        status = fut.result(timeout=DEMO_TIMEOUT)   # the run keeps going if this raises
        if status.get("status") == "done":
            narr = _read_narration(job_id)
            return _demo_payload("L1_LIVE", job_id, status, narr,
                                 model_url=f"/model/{job_id}",
                                 status_url=f"/status/{job_id}")
        l1_error = status.get("error") or "pipeline did not complete"
    except FutureTimeout:
        l1_error = f"live recompute exceeded {DEMO_TIMEOUT:.0f}s"
    except Exception as e:
        l1_error = f"{type(e).__name__}: {e}"
    log.warning("Demo L1 live unavailable (%s) -> falling back to L2 cached.", l1_error)

    # ---- L2 CACHED (committed frozen golden artifact) -----------------------
    if os.path.exists(GOLDEN_GLB) and os.path.exists(GOLDEN_NARR):
        narr = json.load(open(GOLDEN_NARR))
        fst = json.load(open(GOLDEN_STATUS)) if os.path.exists(GOLDEN_STATUS) else {}
        payload = _demo_payload("L2_CACHED", fst.get("job_id"), fst, narr,
                                model_url="/golden/model.glb", status_url="/golden")
        payload["l1_error"] = l1_error
        return payload

    # ---- Nothing to serve ---------------------------------------------------
    raise HTTPException(503, f"Demo L1 failed ({l1_error}) and no frozen golden "
                             f"artifact found. Run `python scripts/freeze_golden.py`.")


def _demo_payload(layer: str, job_id, status: dict, narr: dict,
                  model_url: str, status_url: str | None) -> dict:
    """Uniform /demo response shape across L1/L2."""
    is_synth = status.get("is_synthetic_placeholder", False)
    return {
        "job_id": job_id,
        "status": "done",
        "demo_layer": layer,                 # L1_LIVE | L2_CACHED
        "data_source": status.get("data_source",
                                  "SYNTHETIC_PLACEHOLDER" if is_synth else "REAL"),
        "is_synthetic_placeholder": is_synth,
        "modality": status.get("modality"),
        "stage_modes": {s: info.get("mode") for s, info in status.get("stages", {}).items()},
        "narration": narr.get("narration"),
        "narration_mode": narr.get("mode"),
        "confidence": (narr.get("summary") or {}).get("confidence"),
        "model_url": model_url,
        "status_url": status_url,
    }


# =============================================================================
# Frozen golden artifact (L2 cache served as static files)
# =============================================================================
@app.get("/golden/model.glb")
def golden_model():
    if not os.path.exists(GOLDEN_GLB):
        raise HTTPException(404, "No frozen golden model. Run scripts/freeze_golden.py.")
    return FileResponse(GOLDEN_GLB, media_type="model/gltf-binary",
                        filename="golden.glb")


@app.get("/golden/narration.json")
def golden_narration():
    if not os.path.exists(GOLDEN_NARR):
        raise HTTPException(404, "No frozen golden narration.")
    return FileResponse(GOLDEN_NARR, media_type="application/json")


@app.get("/golden")
def golden_status():
    if not os.path.exists(GOLDEN_STATUS):
        raise HTTPException(404, "No frozen golden status. Run scripts/freeze_golden.py.")
    return FileResponse(GOLDEN_STATUS, media_type="application/json")


# =============================================================================
# Polling / download
# =============================================================================
@app.get("/status/{job_id}")
def status(job_id: str):
    """Full status: current stage + PRIMARY/FALLBACK (or REAL_AI) per stage."""
    st = pipeline.read_status(job_id)
    if st is None:
        raise HTTPException(404, f"Unknown job {job_id}")
    return st


@app.get("/model/{job_id}")
def model(job_id: str):
    """Download the reconstructed .glb."""
    path = pipeline.model_path(job_id)
    if not os.path.exists(path):
        raise HTTPException(404, "Model not ready. Has the pipeline finished? (GET /status)")
    return FileResponse(path, media_type="model/gltf-binary",
                        filename=f"{job_id}.glb")


@app.post("/narrate/{job_id}")
def narrate(job_id: str):
    """(Re)generate narration for a job that has already been processed.

    The structured summary was built during the pipeline run and persisted; this
    re-runs the LLM (or the templated fallback) against it and returns JSON.
    """
    st = pipeline.read_status(job_id)
    if st is None:
        raise HTTPException(404, f"Unknown job {job_id}")
    existing = _read_narration(job_id)
    summary = existing.get("summary")
    if not summary:
        raise HTTPException(409, "No summary yet — run POST /process/{job_id} first.")

    narr = narration.narrate(summary)
    payload = {"narration": narr["text"], "mode": narr["mode"],
               "model": narr["model"], "summary": summary}
    import json
    with open(pipeline.narration_path(job_id), "w") as f:
        json.dump(payload, f, indent=2)
    return payload


# =============================================================================
# Helpers
# =============================================================================
def _read_narration(job_id: str) -> dict:
    path = pipeline.narration_path(job_id)
    if not os.path.exists(path):
        return {}
    import json
    with open(path) as f:
        return json.load(f)
