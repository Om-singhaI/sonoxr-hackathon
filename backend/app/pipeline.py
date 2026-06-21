"""Stage 6 (part) — Orchestration, status, and fallback logic.

This module wires stages 1-5 together, decides PRIMARY vs FALLBACK at each step,
and writes a per-job `status.json` that the /status endpoint serves. It is the
single source of truth for "which path ran" — exactly what the team needs to
answer judging Q&A.

Two entry points:
  * run_pipeline(job_id)  — runs ingestion -> segmentation -> reconstruction ->
                            meshing -> narration for an existing job. Used as a
                            FastAPI BackgroundTask by /process, and directly
                            (synchronously) by /demo.
  * prepare_demo_job()    — builds a fresh job from the bundled, pre-verified
                            sample. This backs the golden /demo path.

Design note: ingestion.py is kept dependency-free of this module, so the import
graph is a clean DAG (main -> pipeline -> stage modules). Job creation + status
live here.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid

from . import (ingestion, preprocessing, segmentation, reconstruction,
               meshing, narration)

log = logging.getLogger("sonoxr.pipeline")

# --- Filesystem layout --------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
DATA_DIR = os.path.join(BASE_DIR, "data")
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
SAMPLE_DIR = os.path.join(DATA_DIR, "sample")
SAMPLE_MANIFEST = os.path.join(SAMPLE_DIR, "sample_manifest.json")

os.makedirs(JOBS_DIR, exist_ok=True)

# Ordered stages tracked in status.json. "ingestion" is the load step;
# "preprocessing" is the (ultrasound-only) conditioning step; the rest are the
# processing stages run by run_pipeline.
STAGE_NAMES = ["ingestion", "preprocessing", "segmentation",
               "reconstruction", "meshing", "narration"]


# =============================================================================
# Job + status helpers
# =============================================================================
def job_dir(job_id: str) -> str:
    return os.path.join(JOBS_DIR, job_id)


def model_path(job_id: str) -> str:
    return os.path.join(job_dir(job_id), "model.glb")


def narration_path(job_id: str) -> str:
    return os.path.join(job_dir(job_id), "narration.json")


def status_path(job_id: str) -> str:
    return os.path.join(job_dir(job_id), "status.json")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def create_job(input_type: str | None = None, source_path: str | None = None,
               anatomy_label: str = "the scanned anatomy",
               is_synthetic_placeholder: bool = False,
               modality: str = "auto",
               data_source: str = "USER_UPLOAD") -> str:
    """Allocate a job id + directory and write the initial status skeleton.

    `modality`: "auto" | "ultrasound" | "ct_mri" — selects whether the US-aware
    preprocessing path runs. `data_source`: "REAL" | "SYNTHETIC_PLACEHOLDER" |
    "USER_UPLOAD" — surfaced so /demo + /status clearly report what ran.
    """
    job_id = uuid.uuid4().hex[:12]
    os.makedirs(job_dir(job_id), exist_ok=True)
    status = {
        "job_id": job_id,
        "input_type": input_type,
        "source_path": source_path,
        "anatomy_label": anatomy_label,
        "is_synthetic_placeholder": is_synthetic_placeholder,
        "modality": modality,                 # auto | ultrasound | ct_mri
        "data_source": data_source,           # REAL | SYNTHETIC_PLACEHOLDER | USER_UPLOAD
        "status": "pending",                 # pending | running | done | error
        "current_stage": None,
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
        "stages": {
            name: {"status": "pending", "mode": None, "detail": ""}
            for name in STAGE_NAMES
        },
        "artifacts": {"glb": None, "narration": None},
    }
    write_status(status)
    return job_id


def read_status(job_id: str) -> dict | None:
    p = status_path(job_id)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def write_status(status: dict) -> None:
    status["updated_at"] = _now()
    p = status_path(status["job_id"])
    # Atomic-ish write so a concurrent /status read never sees a half-written file.
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(status, f, indent=2)
    os.replace(tmp, p)


def _set_stage(status: dict, name: str, stage_status: str,
               mode: str | None = None, detail: str = "") -> None:
    """Update one stage's record and the top-level current_stage, then persist."""
    status["stages"][name]["status"] = stage_status
    if mode is not None:
        status["stages"][name]["mode"] = mode
    if detail:
        status["stages"][name]["detail"] = detail
    if stage_status == "running":
        status["current_stage"] = name
        status["status"] = "running"
    write_status(status)


def _resolve_modality(status: dict, loaded) -> str:
    """Decide whether this volume is ultrasound. Order: explicit override on the
    job > DICOM Modality tag (US/IVUS) > default 'ct_mri' (safe — keeps the
    validated CT/MRI path)."""
    explicit = (status.get("modality") or "auto").lower()
    if explicit in ("ultrasound", "ct_mri"):
        return explicit
    dm = (loaded.meta.get("dicom_modality") or "").upper()
    if dm in ("US", "IVUS", "ECHO"):
        return "ultrasound"
    return "ct_mri"


# =============================================================================
# The pipeline
# =============================================================================
def run_pipeline(job_id: str) -> dict:
    """Run ingestion -> segmentation -> reconstruction -> meshing -> narration.

    Returns the final status dict. Never raises: any unrecoverable error is
    recorded on the status (status="error") so the service stays up.
    """
    status = read_status(job_id)
    if status is None:
        raise FileNotFoundError(f"Unknown job {job_id}")

    try:
        input_type = status.get("input_type")
        src = status.get("source_path")
        if not input_type or not src:
            raise ValueError("Job is missing input_type/source_path.")
        is_volume = ingestion.is_volume_type(input_type)

        # ---------------------------------------------------------------- INGEST
        _set_stage(status, "ingestion", "running")
        spacing = (1.0, 1.0, 1.0)
        volume = frames = None
        is_ultrasound = False
        if is_volume:
            loaded = ingestion.load_volume(src, input_type)
            volume, spacing = loaded.volume, loaded.spacing
            modality = _resolve_modality(status, loaded)
            status["modality"] = modality
            is_ultrasound = (modality == "ultrasound")
            _set_stage(status, "ingestion", "done", loaded.reader_mode,
                       f"{loaded.detail} | modality={modality}")
        else:
            loaded = ingestion.load_frames(src, input_type)
            frames, spacing = loaded.frames, loaded.spacing
            _set_stage(status, "ingestion", "done", loaded.reader_mode, loaded.detail)

        # ----------------------------------------------------- PREPROCESSING (US)
        # Only ultrasound VOLUMES get conditioned. CT/MRI and the 2D path skip
        # this entirely, so the validated CT/MRI path is byte-for-byte unchanged.
        _set_stage(status, "preprocessing", "running")
        seg_input = volume
        if is_volume and is_ultrasound:
            try:
                pre = preprocessing.preprocess_ultrasound(volume, spacing)
                seg_input = pre.volume
                _set_stage(status, "preprocessing", "done", pre.method, pre.detail)
            except Exception as e:
                # Never let conditioning break the run — fall back to the raw volume.
                log.warning("US preprocessing failed (%s); using raw volume.", e)
                seg_input = volume
                _set_stage(status, "preprocessing", "done", "FALLBACK(raw)",
                           f"Preprocessing failed ({type(e).__name__}); used raw volume.")
        else:
            why = "non-ultrasound volume" if is_volume else "2D fallback path"
            _set_stage(status, "preprocessing", "skipped", "NONE",
                       f"Skipped (preprocessing applies to ultrasound volumes only; {why}).")

        # ----------------------------------------------------------- SEGMENTATION
        _set_stage(status, "segmentation", "running")
        if is_volume:
            seg = segmentation.segment_volume(seg_input, spacing,
                                              ultrasound=is_ultrasound)   # PRIMARY
        else:
            seg = segmentation.segment_frames(frames)                     # FALLBACK
        _set_stage(status, "segmentation", "done", seg.mode, seg.detail)

        # ---------------------------------------------------------- RECONSTRUCTION
        _set_stage(status, "reconstruction", "running")
        recon = _reconstruct(seg, spacing, is_volume, src)
        _set_stage(status, "reconstruction", "done", recon.mode, recon.detail)

        # ---------------------------------------------------------------- MESHING
        _set_stage(status, "meshing", "running")
        mesh_stats = meshing.build_and_export(
            recon.verts, recon.faces, model_path(job_id), normals=recon.normals)
        # Meshing has no real "fallback" mode; mark PRIMARY, but flag if decimation
        # was skipped (e.g. fast-simplification missing) in the detail string.
        mesh_mode = "PRIMARY" if mesh_stats.decimated else "PRIMARY (no decimation)"
        _set_stage(status, "meshing", "done", mesh_mode, mesh_stats.detail)
        status["artifacts"]["glb"] = model_path(job_id)

        # -------------------------------------------------------------- NARRATION
        _set_stage(status, "narration", "running")
        summary = narration.build_summary(
            status=status,
            seg_confidence=seg.confidence,
            mesh_stats=mesh_stats,
            recon_meta=recon.meta,
            anatomy_label=status.get("anatomy_label", "the scanned anatomy"),
            is_synthetic_placeholder=status.get("is_synthetic_placeholder", False),
        )
        narr = narration.narrate(summary)
        # Persist narration + the summary we fed it (great for the demo + debugging).
        with open(narration_path(job_id), "w") as f:
            json.dump({"narration": narr["text"], "mode": narr["mode"],
                       "model": narr["model"], "summary": summary}, f, indent=2)
        _set_stage(status, "narration", "done", narr["mode"], narr["detail"])
        status["artifacts"]["narration"] = narration_path(job_id)

        # ------------------------------------------------------------------- DONE
        status["status"] = "done"
        status["current_stage"] = "done"
        write_status(status)
        log.info("Pipeline complete for job %s.", job_id)

    except Exception as e:
        # Robustness: never let an exception escape the background task / request.
        log.exception("Pipeline failed for job %s", job_id)
        status = read_status(job_id) or status
        status["status"] = "error"
        status["error"] = f"{type(e).__name__}: {e}"
        # Mark the running stage (if any) as errored.
        for name in STAGE_NAMES:
            if status["stages"][name]["status"] == "running":
                status["stages"][name]["status"] = "error"
        write_status(status)

    return status


def _reconstruct(seg, spacing, is_volume: bool, src: str):
    """Reconstruction with the stretch/fallback ladder.

    Volume input  -> marching cubes on the real 3D mask (PRIMARY).
    2D input      -> try the UltrasODM stretch upgrade (assume it fails), then
                     fall back to the low-fidelity uniform voxel stack.
    """
    if is_volume:
        return reconstruction.reconstruct_from_volume(seg.mask, spacing)

    # --- 2D path: attempt the stretch upgrade first, silently fall back. -------
    points = reconstruction.try_ultrasodm(src)            # almost always None
    if points is not None:
        poisson = reconstruction.poisson_from_pointcloud(points)
        if poisson is not None:
            verts, faces = poisson
            import numpy as np
            return reconstruction.ReconResult(
                verts=verts, faces=faces,
                normals=np.zeros_like(verts),
                mode="FALLBACK",
                detail="UltrasODM point cloud + Open3D Poisson (STRETCH path).",
                meta={"voxel_count": len(verts), "spacing": spacing})
    # Default robustness fallback (documented low fidelity).
    return reconstruction.reconstruct_from_frames_voxel_stack(seg.mask, spacing)


# =============================================================================
# Golden demo path
# =============================================================================
def read_sample_manifest() -> dict | None:
    if not os.path.exists(SAMPLE_MANIFEST):
        return None
    with open(SAMPLE_MANIFEST) as f:
        return json.load(f)


def _find_demo_real_volume() -> tuple[str, str] | None:
    """Locate a REAL volume for /demo (FIX 5). Order:
       1. $DEMO_VOLUME_PATH if set and existing.
       2. A volume dropped at the TOP LEVEL of data/sample/real/ (the documented
          "drop your real echo here" location). Returns (path, input_type).
    Example sub-directories (brain_mri/, cell_nuclei/, ct_head/) are intentionally
    NOT picked up — only top-level drops count, so verification data never
    contaminates the demo."""
    env = os.environ.get("DEMO_VOLUME_PATH")
    if env and os.path.exists(env):
        low = env.lower()
        if os.path.isdir(env):
            return env, "dicom_series_dir"
        if low.endswith(".nii") or low.endswith(".nii.gz"):
            return env, "nifti_volume"
        return env, "dicom"

    real_dir = os.path.join(SAMPLE_DIR, "real")
    if os.path.isdir(real_dir):
        for f in sorted(os.listdir(real_dir)):
            full = os.path.join(real_dir, f)
            low = f.lower()
            if os.path.isfile(full) and (low.endswith(".nii") or low.endswith(".nii.gz")):
                return full, "nifti_volume"
            if os.path.isfile(full) and low.endswith(".dcm"):
                return full, "dicom"
        # A top-level folder of DICOM slices = a real multi-slice SERIES. Require
        # >= 2 .dcm so a single 2D-cine file (e.g. data/sample/real/echo/A_0.dcm,
        # which is 2D+time, handled by the separate echo demo) is NOT mistaken for
        # a 3D volume and routed into the volume pipeline.
        for f in sorted(os.listdir(real_dir)):
            full = os.path.join(real_dir, f)
            if os.path.isdir(full):
                dcms = [x for x in os.listdir(full) if x.lower().endswith(".dcm")]
                if len(dcms) >= 2:
                    return full, "dicom_series_dir"
    return None


def prepare_demo_job() -> str:
    """Create the golden-/demo job (FIX 5).

    Prefers a REAL volume ($DEMO_VOLUME_PATH or a top-level drop in
    data/sample/real/); otherwise falls back to the labeled SYNTHETIC PLACEHOLDER
    from the sample manifest. The job's data_source/is_synthetic_placeholder make
    /demo + /status report unambiguously whether REAL or SYNTHETIC data ran.

    Raises FileNotFoundError with clear guidance if nothing is available.
    """
    real = _find_demo_real_volume()
    if real is not None:
        src, input_type = real
        job_id = create_job(
            input_type=input_type, source_path=src,
            anatomy_label="a real 3D echocardiography / ultrasound volume",
            is_synthetic_placeholder=False,
            modality="ultrasound",          # treat the demo real volume as echo/US
            data_source="REAL")
        log.info("Prepared demo job %s from REAL volume %s.", job_id, src)
        return job_id

    # Fall back to the labeled synthetic placeholder.
    manifest = read_sample_manifest()
    if manifest is None:
        raise FileNotFoundError(
            "No real volume and no sample manifest found. Run "
            "`python scripts/download_sample_data.py` (fetches a real volume or "
            "generates the labeled synthetic placeholder), or set DEMO_VOLUME_PATH.")
    src = manifest["path"]
    if not os.path.exists(src):
        raise FileNotFoundError(
            f"Sample manifest points at '{src}', which does not exist. "
            "Re-run `python scripts/download_sample_data.py`.")
    is_synth = manifest.get("is_synthetic_placeholder", False)
    job_id = create_job(
        input_type=manifest.get("input_type", "dicom_series_dir"),
        source_path=src,
        anatomy_label=manifest.get("anatomy_label", "the scanned anatomy"),
        is_synthetic_placeholder=is_synth,
        modality=manifest.get("modality", "auto"),
        data_source="SYNTHETIC_PLACEHOLDER" if is_synth else "REAL")
    log.info("Prepared demo job %s from sample %s (synthetic=%s).",
             job_id, src, is_synth)
    return job_id
