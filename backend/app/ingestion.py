"""Stage 1 — Ingestion.

Turns whatever the frontend uploaded into something the rest of the pipeline
can consume:

  * a VOLUMETRIC ultrasound (3D/4D DICOM, a DICOM series, or NIfTI)   -> PRIMARY
        read into a 3D numpy array (z, y, x) with REAL voxel spacing.
  * a video / zip of 2D frames                                       -> FALLBACK
        decoded into a list of 2D grayscale frames (robustness only).

This module is intentionally *pure*: it does not know about jobs, status files
or the web layer. It just detects types and loads pixels. pipeline.py wires it
into the orchestration. That keeps the import graph a clean DAG
(main -> pipeline -> {ingestion, segmentation, ...}) with no cycles.

PRIMARY DICOM reader is SimpleITK (robust for medical volumes + spacing). If the
SimpleITK wheel is unavailable (it can lag on bleeding-edge Python), we fall
back to pydicom. Either way we PRESERVE VOXEL SPACING from the header, because
spacing is what makes the final mesh correctly proportioned.
"""

from __future__ import annotations

import logging
import os
import zipfile
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

log = logging.getLogger("sonoxr.ingestion")

# --- Optional heavy deps: import defensively so a missing wheel never crashes
#     the service at import time. We branch on these flags at call sites. -------
try:
    import SimpleITK as sitk  # PREFERRED volumetric DICOM/NIfTI reader

    _HAS_SITK = True
except Exception as e:  # pragma: no cover - environment dependent
    _HAS_SITK = False
    log.warning("SimpleITK unavailable (%s); DICOM reads will use pydicom fallback.", e)

try:
    import pydicom  # fallback DICOM reader

    _HAS_PYDICOM = True
except Exception as e:  # pragma: no cover
    _HAS_PYDICOM = False
    log.warning("pydicom unavailable (%s).", e)

try:
    import cv2  # only needed for the 2D robustness path (video/frames)

    _HAS_CV2 = True
except Exception as e:  # pragma: no cover
    _HAS_CV2 = False
    log.warning("OpenCV (cv2) unavailable (%s); video/frame ingestion disabled.", e)


# Input type constants. The first three are VOLUME types (-> primary 3D path);
# the last two are 2D types (-> robustness fallback path).
VOLUME_TYPES = ("dicom", "dicom_series_zip", "dicom_series_dir", "nifti_volume")
TWO_D_TYPES = ("video", "frames_zip")

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")
VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")


@dataclass
class LoadedVolume:
    """Result of loading a volumetric input."""

    volume: np.ndarray                       # 3D float32 array, shape (z, y, x)
    spacing: tuple[float, float, float]      # (sz, sy, sx) in mm — REAL, from header
    reader_mode: str                         # "PRIMARY" (SimpleITK) or "FALLBACK" (pydicom)
    detail: str                              # human-readable note for /status
    meta: dict = field(default_factory=dict)


@dataclass
class LoadedFrames:
    """Result of loading a 2D (video/frames) input — robustness path only."""

    frames: list[np.ndarray]                 # list of 2D float32 grayscale frames
    # Pseudo-spacing for the 2D path. NOTE: the z component is FABRICATED (frames
    # are not spatially registered) — this is exactly why the 2D path is low
    # fidelity and not for the demo. See reconstruction.py.
    spacing: tuple[float, float, float]
    reader_mode: str                         # always "FALLBACK"
    detail: str
    meta: dict = field(default_factory=dict)


# =============================================================================
# Type detection
# =============================================================================
def detect_input_type(filename: str, sample_path: Optional[str] = None) -> str:
    """Best-effort classification of an uploaded file.

    Uses the extension first, then peeks inside zips and sniffs the DICOM
    "DICM" magic number for extension-less / mislabeled files. Returns one of
    VOLUME_TYPES + TWO_D_TYPES, or "unknown".
    """
    name = (filename or "").lower()
    ext = os.path.splitext(name)[1]

    if name.endswith(".nii") or name.endswith(".nii.gz"):
        return "nifti_volume"
    if ext == ".dcm":
        return "dicom"
    if ext in VIDEO_EXTS:
        return "video"
    if ext == ".zip":
        return _classify_zip(sample_path) if sample_path else "frames_zip"

    # No useful extension — sniff the file content if we have it on disk.
    if sample_path and os.path.isfile(sample_path):
        if _is_dicom_magic(sample_path):
            return "dicom"
        if zipfile.is_zipfile(sample_path):
            return _classify_zip(sample_path)

    log.warning("Could not confidently classify '%s'; returning 'unknown'.", filename)
    return "unknown"


def is_volume_type(input_type: str) -> bool:
    """True if this input drives the PRIMARY 3D-volume path."""
    return input_type in VOLUME_TYPES


def _is_dicom_magic(path: str) -> bool:
    """DICOM files carry the ASCII magic 'DICM' at byte offset 128."""
    try:
        with open(path, "rb") as f:
            f.seek(128)
            return f.read(4) == b"DICM"
    except Exception:
        return False


def _classify_zip(path: str) -> str:
    """Peek inside a zip: DICOM series vs a bag of image frames."""
    try:
        with zipfile.ZipFile(path) as zf:
            names = [n.lower() for n in zf.namelist() if not n.endswith("/")]
    except Exception as e:
        log.warning("Could not read zip %s (%s); assuming frames_zip.", path, e)
        return "frames_zip"
    if any(n.endswith(".dcm") for n in names):
        return "dicom_series_zip"
    if any(n.endswith(".nii") or n.endswith(".nii.gz") for n in names):
        return "nifti_volume"
    if any(os.path.splitext(n)[1] in IMAGE_EXTS for n in names):
        return "frames_zip"
    # Series exported without .dcm extensions is common — sniff a member.
    try:
        with zipfile.ZipFile(path) as zf:
            for n in zf.namelist():
                if n.endswith("/"):
                    continue
                with zf.open(n) as fh:
                    head = fh.read(132)
                if len(head) >= 132 and head[128:132] == b"DICM":
                    return "dicom_series_zip"
    except Exception:
        pass
    return "frames_zip"


# =============================================================================
# Volume loading (PRIMARY path)
# =============================================================================
def load_volume(path: str, input_type: str) -> LoadedVolume:
    """Load any VOLUME-type input into a 3D array + real spacing.

    `path` may be a single file (.dcm/.nii) OR a directory containing a DICOM
    series OR a .zip of a series. Dispatches to SimpleITK (PRIMARY) and falls
    back to pydicom (FALLBACK) on any failure.
    """
    # A directory of DICOM slices (e.g. the bundled phantom) — read as a series.
    # Checked FIRST so a directory is never mistaken for a zip.
    if os.path.isdir(path):
        return _load_dicom_dir(path)

    # A zip of a series: extract next to itself, then read the directory.
    if input_type == "dicom_series_zip" or (path.endswith(".zip")):
        series_dir = _extract_zip(path)
        return _load_dicom_dir(series_dir)

    if input_type == "nifti_volume":
        return _load_with_sitk_file(path, expect="NIfTI")

    # Single .dcm (possibly an enhanced/multi-frame volume) ---------------------
    try:
        return _load_with_sitk_file(path, expect="DICOM")
    except Exception as e:
        log.warning("SimpleITK single-file read failed (%s); trying pydicom.", e)
        return _load_single_dicom_pydicom(path)


def _extract_zip(path: str) -> str:
    out_dir = path + "_extracted"
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        zf.extractall(out_dir)
    return out_dir


def _load_with_sitk_file(path: str, expect: str) -> LoadedVolume:
    """Read a single multi-frame DICOM or a NIfTI volume with SimpleITK."""
    if not _HAS_SITK:
        raise RuntimeError("SimpleITK not installed")
    img = sitk.ReadImage(path)
    return _sitk_to_loaded(img, mode="PRIMARY",
                           detail=f"{expect} read via SimpleITK (preserves spacing).",
                           modality=_sitk_modality_from_image(img))


def _load_dicom_dir(directory: str) -> LoadedVolume:
    """Read a directory of DICOM slices as a single 3D volume.

    PRIMARY: SimpleITK's ImageSeriesReader (sorts slices by geometry, robust).
    FALLBACK: pydicom — sort by ImagePositionPatient/InstanceNumber and stack.
    """
    if _HAS_SITK:
        try:
            reader = sitk.ImageSeriesReader()
            reader.MetaDataDictionaryArrayUpdateOn()  # so we can read the Modality tag
            reader.LoadPrivateTagsOn()
            # If multiple series live in the same folder, take the first/largest.
            ids = reader.GetGDCMSeriesIDs(directory)
            if ids:
                files = reader.GetGDCMSeriesFileNames(directory, ids[0])
            else:
                files = reader.GetGDCMSeriesFileNames(directory)
            if files:
                reader.SetFileNames(files)
                img = reader.Execute()
                modality = None
                try:
                    if reader.HasMetaDataKey(0, "0008|0060"):
                        modality = reader.GetMetaData(0, "0008|0060").strip() or None
                except Exception:
                    pass
                return _sitk_to_loaded(
                    img, mode="PRIMARY", modality=modality,
                    detail=f"DICOM series ({len(files)} slices) via SimpleITK.")
            log.warning("SimpleITK found no series in %s; trying pydicom.", directory)
        except Exception as e:
            log.warning("SimpleITK series read failed (%s); trying pydicom.", e)
    return _load_dicom_dir_pydicom(directory)


def _sitk_to_loaded(img, mode: str, detail: str,
                    modality: str | None = None) -> LoadedVolume:
    """Convert a SimpleITK image to our LoadedVolume (array + (sz,sy,sx))."""
    arr = sitk.GetArrayFromImage(img).astype(np.float32)  # -> (z, y, x)
    if arr.ndim == 4:
        # 4D (e.g. a 4D-echo time series) — take the first volume for the demo.
        log.info("4D input detected %s; using first temporal volume.", arr.shape)
        arr = arr[0]
    sx, sy, sz = img.GetSpacing()  # SimpleITK returns (x, y, z)
    spacing = (float(sz), float(sy), float(sx))
    meta = {"origin": img.GetOrigin(), "size_xyz": img.GetSize(),
            "dicom_modality": modality}
    log.info("Loaded volume %s, spacing(z,y,x)=%s [%s] modality=%s",
             arr.shape, spacing, mode, modality)
    return LoadedVolume(volume=arr, spacing=spacing, reader_mode=mode,
                        detail=detail, meta=meta)


def _sitk_modality_from_image(img) -> str | None:
    """Read the DICOM Modality tag (0008|0060) from a SimpleITK image, if present."""
    try:
        if img.HasMetaDataKey("0008|0060"):
            return img.GetMetaData("0008|0060").strip() or None
    except Exception:
        pass
    return None


# --- pydicom fallbacks -------------------------------------------------------
def _load_single_dicom_pydicom(path: str) -> LoadedVolume:
    if not _HAS_PYDICOM:
        raise RuntimeError("Neither SimpleITK nor pydicom available to read DICOM.")
    ds = pydicom.dcmread(path)
    arr = ds.pixel_array.astype(np.float32)
    if arr.ndim == 2:
        # A single 2D slice is not a real volume — keep it as a thin 1-slice
        # volume so downstream code does not crash, but flag it loudly.
        log.warning("Single 2D DICOM slice — NOT a real volume. Mesh will be flat.")
        arr = arr[np.newaxis, ...]
    spacing = _pydicom_spacing(ds)
    return LoadedVolume(
        volume=arr, spacing=spacing, reader_mode="FALLBACK",
        detail="Single/multi-frame DICOM via pydicom (SimpleITK unavailable).",
        meta={"sop": str(getattr(ds, "SOPClassUID", "")),
              "dicom_modality": str(getattr(ds, "Modality", "") or "") or None})


def _load_dicom_dir_pydicom(directory: str) -> LoadedVolume:
    if not _HAS_PYDICOM:
        raise RuntimeError("Neither SimpleITK nor pydicom available to read DICOM.")
    paths = []
    for root, _dirs, files in os.walk(directory):
        for fn in files:
            paths.append(os.path.join(root, fn))
    slices = []
    for p in paths:
        try:
            slices.append(pydicom.dcmread(p))
        except Exception:
            continue  # skip non-DICOM members silently
    if not slices:
        raise RuntimeError(f"No readable DICOM slices found in {directory}")

    # Sort by through-plane position when available, else InstanceNumber.
    def sort_key(ds):
        ipp = getattr(ds, "ImagePositionPatient", None)
        if ipp is not None and len(ipp) == 3:
            return float(ipp[2])
        return float(getattr(ds, "InstanceNumber", 0) or 0)

    slices.sort(key=sort_key)
    arr = np.stack([s.pixel_array.astype(np.float32) for s in slices], axis=0)
    spacing = _pydicom_spacing(slices[0], slices)
    log.info("Loaded volume %s via pydicom, spacing(z,y,x)=%s [FALLBACK]",
             arr.shape, spacing)
    return LoadedVolume(
        volume=arr, spacing=spacing, reader_mode="FALLBACK",
        detail=f"DICOM series ({len(slices)} slices) via pydicom (SimpleITK unavailable).",
        meta={"dicom_modality": str(getattr(slices[0], "Modality", "") or "") or None})


def _pydicom_spacing(ds, slices=None) -> tuple[float, float, float]:
    """Recover (sz, sy, sx) spacing in mm from pydicom headers, with sane defaults."""
    ps = getattr(ds, "PixelSpacing", None)  # [row(y), col(x)] in mm
    sy, sx = (float(ps[0]), float(ps[1])) if ps else (1.0, 1.0)
    # Through-plane spacing: prefer the geometric gap between the first two
    # slices; else SpacingBetweenSlices; else SliceThickness; else 1mm.
    sz = None
    if slices and len(slices) >= 2:
        z0 = getattr(slices[0], "ImagePositionPatient", None)
        z1 = getattr(slices[1], "ImagePositionPatient", None)
        if z0 and z1:
            sz = abs(float(z1[2]) - float(z0[2]))
    if not sz:
        sz = float(getattr(ds, "SpacingBetweenSlices", 0) or 0) or \
             float(getattr(ds, "SliceThickness", 0) or 0) or 1.0
    return (float(sz), sy, sx)


# =============================================================================
# Echo cine loading (iteration 5) — REAL 2D echocardiography cine (2D + time)
# =============================================================================
@dataclass
class LoadedCine:
    """A real 2D ultrasound cine loop (multi-frame US DICOM): 2D + TIME.

    This is NOT a 3D volume — the third axis is the cardiac cycle. See
    app/echo_cycle.py for the honest cycle analysis built on top of it.
    """
    frames: np.ndarray                  # (T, H, W) float32 grayscale, US-region cropped
    fps: float                          # frames per second (from FrameTime)
    cm_per_px: float                    # isotropic in-plane calibration (cm/pixel), 0 if unknown
    region_box: tuple                   # (x0, y0, x1, y1) of the chosen US region in the full frame
    n_regions: int
    detail: str
    meta: dict = field(default_factory=dict)


def load_echo_cine(path: str, region_index: int = 0,
                   drop_bottom_frac: float = 0.10) -> LoadedCine:
    """Load a multi-frame US DICOM cine, crop to one ultrasound region, return
    grayscale frames + calibration. Drops the bottom strip (ECG trace) by default.

    Uses the luma (Y) channel for YBR data (the B-mode brightness); converts RGB
    otherwise. pydicom path (SimpleITK flattens the RGB cine awkwardly).
    """
    if not _HAS_PYDICOM:
        raise RuntimeError("pydicom required to read the echo cine.")
    ds = pydicom.dcmread(path)
    arr = ds.pixel_array                                   # (T,H,W,3) or (T,H,W)
    photometric = str(getattr(ds, "PhotometricInterpretation", "")).upper()
    if arr.ndim == 4:
        if "YBR" in photometric:
            gray = arr[..., 0].astype(np.float32)          # Y = luma = B-mode brightness
        else:
            gray = np.stack([cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in arr]).astype(np.float32) \
                   if _HAS_CV2 else arr[..., 0].astype(np.float32)
    elif arr.ndim == 3:
        gray = arr.astype(np.float32)                      # already (T,H,W) mono
    else:
        raise RuntimeError(f"Unexpected echo pixel_array ndim={arr.ndim}")

    # Ultrasound region (the sector) + calibration.
    regions = getattr(ds, "SequenceOfUltrasoundRegions", None)
    cm_per_px = 0.0
    if regions and len(regions) > region_index:
        r = regions[region_index]
        x0 = int(getattr(r, "RegionLocationMinX0", 0)); y0 = int(getattr(r, "RegionLocationMinY0", 0))
        x1 = int(getattr(r, "RegionLocationMaxX1", gray.shape[2])); y1 = int(getattr(r, "RegionLocationMaxY1", gray.shape[1]))
        dx = float(getattr(r, "PhysicalDeltaX", 0) or 0)
        cm_per_px = abs(dx)                                 # isotropic in-plane (cm/px)
    else:
        x0, y0, x1, y1 = 0, 0, gray.shape[2], gray.shape[1]
    y1 = y0 + int((1.0 - drop_bottom_frac) * (y1 - y0))     # drop ECG strip
    crop = gray[:, y0:y1, x0:x1]

    fps = 0.0
    ft = getattr(ds, "FrameTime", None)
    if ft:
        try:
            fps = 1000.0 / float(ft)
        except Exception:
            fps = 0.0
    if not fps:
        fps = float(getattr(ds, "CineRate", 0) or 0) or 15.0

    log.info("Echo cine: %d frames, region %d %s, %.1f fps, %.4f cm/px",
             crop.shape[0], region_index, (x0, y0, x1, y1), fps, cm_per_px)
    return LoadedCine(
        frames=crop, fps=fps, cm_per_px=cm_per_px,
        region_box=(x0, y0, x1, y1),
        n_regions=len(regions) if regions else 1,
        detail=(f"Real 2D US cine ({crop.shape[0]} frames, region {region_index}); "
                f"2D+time (NOT a 3D volume). modality={getattr(ds,'Modality','US')}."),
        meta={"modality": str(getattr(ds, "Modality", "US")),
              "sop_class": str(getattr(ds, "SOPClassUID", "")),
              "two_d_plus_time": True})


# =============================================================================
# 2D loading (ROBUSTNESS FALLBACK path only)
# =============================================================================
def load_frames(path: str, input_type: str, max_frames: int = 200) -> LoadedFrames:
    """Decode a video or a zip of images into 2D grayscale frames.

    ROBUSTNESS ONLY. These frames have no real spatial registration, so the
    reconstruction built from them is low fidelity (see reconstruction.py).
    """
    if input_type == "video":
        frames = _frames_from_video(path, max_frames)
        detail = f"{len(frames)} frames decoded from video via OpenCV."
    else:  # frames_zip
        frames = _frames_from_zip(path, max_frames)
        detail = f"{len(frames)} image frames read from zip."
    if not frames:
        raise RuntimeError("No frames could be decoded from the 2D input.")
    # Pseudo-spacing: in-plane 1mm; through-plane is FABRICATED (1mm) — there is
    # no real depth axis for freehand frames. Flagged everywhere downstream.
    return LoadedFrames(frames=frames, spacing=(1.0, 1.0, 1.0),
                        reader_mode="FALLBACK", detail=detail,
                        meta={"fabricated_depth_axis": True})


def _frames_from_video(path: str, max_frames: int) -> list[np.ndarray]:
    if not _HAS_CV2:
        raise RuntimeError("OpenCV not installed; cannot decode video.")
    cap = cv2.VideoCapture(path)
    frames: list[np.ndarray] = []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    step = max(1, total // max_frames) if total else 1
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
            frames.append(gray)
        i += 1
    cap.release()
    return frames


def _frames_from_zip(path: str, max_frames: int) -> list[np.ndarray]:
    if not _HAS_CV2:
        raise RuntimeError("OpenCV not installed; cannot read image frames.")
    out: list[np.ndarray] = []
    with zipfile.ZipFile(path) as zf:
        names = sorted(n for n in zf.namelist()
                       if os.path.splitext(n.lower())[1] in IMAGE_EXTS)
        for n in names[:max_frames]:
            data = np.frombuffer(zf.read(n), np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                out.append(img.astype(np.float32))
    return out
