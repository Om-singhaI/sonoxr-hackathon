#!/usr/bin/env python3
"""Obtain the bundled sample volume for the golden /demo path.

Order of preference:
  1. A REAL volumetric ultrasound you have already placed in data/sample/real/
     (a .dcm / .nii / .nii.gz file, or a folder of DICOM slices). PREFERRED.
  2. A REAL volume fetched from a known public source (best-effort; these links
     are flaky and may require manual download — we do NOT pretend otherwise).
  3. A clearly-labeled SYNTHETIC PLACEHOLDER phantom we generate locally, so the
     pipeline is always testable. It is marked unmistakably as synthetic in the
     manifest, in logs, and (downstream) in the narration input.

It writes data/sample/sample_manifest.json describing what was chosen:
    { "path", "input_type", "anatomy_label", "is_synthetic_placeholder", "note" }

!!! IMPORTANT !!!  A placeholder must NEVER masquerade as a real reconstruction.
If you see "SYNTHETIC PLACEHOLDER" anywhere, replace data/sample with a real scan
before the judged demo. Instructions for doing so are printed below.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

# --- Paths --------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLE_DIR = os.path.join(ROOT, "data", "sample")
REAL_DIR = os.path.join(SAMPLE_DIR, "real")          # put a real scan here
PHANTOM_DIR = os.path.join(SAMPLE_DIR, "phantom_dicom")
MANIFEST = os.path.join(SAMPLE_DIR, "sample_manifest.json")

VOL_EXTS = (".dcm", ".nii", ".nii.gz")

# Target modality is now 3D ECHOCARDIOGRAPHY (3D fetal US is largely access-
# restricted; 3D echo is more obtainable). These are intentionally documented
# rather than blindly trusted — programmatic, license-clean fetching of a real
# 3D echo/US volume is unreliable and several sources require registration. We
# attempt what we can and are honest when a wall is hit; the printed manual
# instructions are the real deliverable.
PUBLIC_SOURCES = [
    {
        "name": "CETUS — 3D echocardiography challenge",
        "where": "Cardiac Acquisitions for Multi-structure Ultrasound Segmentation / "
                 "CETUS (creatis.insa-lyon.fr / Grand-Challenge). 3D echo volumes; "
                 "free but requires registration.",
    },
    {
        "name": "Zenodo '3D echocardiography' / '3D ultrasound' deposits",
        "where": "Search zenodo.org for '3D echocardiography' or '3D ultrasound "
                 "volume'. Some deposits expose a DIRECT file URL — paste it into "
                 "the ECHO_VOLUME_URL env var (below) for auto-fetch.",
    },
    {
        "name": "Grand-Challenge ultrasound datasets",
        "where": "grand-challenge.org → ultrasound/echo challenges (e.g. CAMUS for "
                 "2D, 3D-echo sets). Usually require an account.",
    },
    {
        "name": "Your own scanner export",
        "where": "A GE/Voluson '.vol' or a 3D-echo cartesian export — convert to "
                 "NIfTI (see the manual instructions printed by this script).",
    },
]

# If the team finds a DIRECT download URL for a real echo/US volume, set this env
# var and re-run — the script fetches + validates it (no hardcoded URLs we can't
# vouch for). Accepts a .nii/.nii.gz, a .dcm, or a .zip of a DICOM series.
ECHO_VOLUME_URL_ENV = "ECHO_VOLUME_URL"


# =============================================================================
# 1. Look for a real scan the user already placed
# =============================================================================
def find_real_volume() -> tuple[str, str] | None:
    """Return (path, input_type) if a real volume is present in data/sample/real/."""
    if not os.path.isdir(REAL_DIR):
        return None
    entries = sorted(os.listdir(REAL_DIR))
    # A nested folder of DICOM slices?
    for e in entries:
        full = os.path.join(REAL_DIR, e)
        if os.path.isdir(full) and any(f.lower().endswith(".dcm") for f in os.listdir(full)):
            return full, "dicom_series_dir"
    # Loose DICOM slices directly in real/ -> treat the folder as a series.
    if any(f.lower().endswith(".dcm") for f in entries):
        return REAL_DIR, "dicom_series_dir"
    # A single multi-frame DICOM or a NIfTI volume.
    for e in entries:
        low = e.lower()
        if low.endswith(".nii") or low.endswith(".nii.gz"):
            return os.path.join(REAL_DIR, e), "nifti_volume"
        if low.endswith(".dcm"):
            return os.path.join(REAL_DIR, e), "dicom"
    return None


# =============================================================================
# 2a. Best-effort auto-fetch of a real echo/US volume (honest about walls)
# =============================================================================
def _looks_like_volume(path: str) -> str | None:
    """Validate a downloaded file is actually a volume (not a login/HTML page).
    Returns an input_type or None."""
    try:
        with open(path, "rb") as f:
            head = f.read(264)
    except Exception:
        return None
    low = path.lower()
    if head[:6].lower().startswith(b"<html") or b"<!doctype html" in head[:64].lower():
        return None                                   # a login / error page
    if head[:2] == b"\x1f\x8b" and (low.endswith(".nii.gz") or low.endswith(".gz")):
        return "nifti_volume"                          # gzip (assume NIfTI)
    if b"n+1\x00" in head[:352] or low.endswith(".nii"):
        return "nifti_volume"                          # NIfTI magic
    if head[:2] == b"PK":
        return "dicom_series_zip"                      # a zip (assume DICOM series)
    if len(head) >= 132 and head[128:132] == b"DICM":
        return "dicom"                                 # DICOM magic
    return None


def attempt_fetch_real_echo() -> tuple[str, str] | None:
    """Try to download a real echo/US volume from ECHO_VOLUME_URL (if set).

    We do NOT hardcode source URLs we can't vouch for. If the team has a direct
    link, set ECHO_VOLUME_URL and we fetch + validate it. We detect HTML/login
    walls and refuse to pretend a registration page is a volume. Returns
    (path, input_type) on success, else None.
    """
    import urllib.request

    url = os.environ.get(ECHO_VOLUME_URL_ENV)
    if not url:
        print(f"({ECHO_VOLUME_URL_ENV} not set — skipping auto-fetch. "
              f"Set it to a DIRECT echo/US volume URL to enable.)")
        return None

    os.makedirs(REAL_DIR, exist_ok=True)
    name = os.path.basename(url.split("?")[0]) or "echo_volume.bin"
    dest = os.path.join(REAL_DIR, name)
    print(f"Attempting auto-fetch: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SonoXR/2.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            ctype = r.headers.get("Content-Type", "")
            if "text/html" in ctype:
                print(f"  -> server returned HTML ({ctype}); likely a "
                      f"registration/login wall. NOT pretending this is a volume.")
                return None
            with open(dest, "wb") as out:
                out.write(r.read())
    except Exception as e:
        print(f"  -> fetch failed ({type(e).__name__}: {e}). Falling back.")
        return None

    itype = _looks_like_volume(dest)
    if itype is None:
        print("  -> downloaded file is NOT a recognizable volume "
              "(probably an HTML page). Removing; falling back.")
        try:
            os.remove(dest)
        except Exception:
            pass
        return None
    print(f"  -> fetched a real volume: {dest} (input_type={itype})")
    return dest, itype


# =============================================================================
# 2b. Manual instructions (the realistic path for a real echo volume)
# =============================================================================
def print_real_data_instructions() -> None:
    print("\n" + "=" * 74)
    print(" COULD NOT auto-fetch a real 3D echo / ultrasound volume.")
    print(" Use the manual path (takes ~3 minutes):")
    print("")
    print(" A) If you have a GE / Voluson '.vol' (or any 3D-echo/US export):")
    print("    1. Open 3D Slicer (free: https://download.slicer.org).")
    print("    2. File > Add Data > choose the .vol (or DICOMDIR / series folder).")
    print("       - For a raw .vol, Slicer may prompt for dims/spacing; or install")
    print("         the 'SlicerHeart' extension which reads GE Kretz .vol natively.")
    print("    3. File > Save Data > pick the loaded volume node > set type to")
    print("       'NIfTI (.nii.gz)' > save it.")
    print(f"    4. Drop the .nii.gz at the TOP LEVEL of:  {REAL_DIR}/")
    print("    5. Re-run:  python scripts/download_sample_data.py")
    print("       (/demo will then auto-use it as REAL data — see FIX 5.)")
    print("")
    print(" B) If you have a direct download URL for a real echo/US volume:")
    print(f"    export {ECHO_VOLUME_URL_ENV}='https://.../volume.nii.gz'")
    print("    python scripts/download_sample_data.py")
    print("")
    print(" Accepted formats in data/sample/real/: .nii / .nii.gz, a multi-frame")
    print(" .dcm, a .zip of a DICOM series, or a folder of DICOM slices.")
    print(" Suggested public sources:")
    for s in PUBLIC_SOURCES:
        print(f"   - {s['name']}\n       {s['where']}")
    print("=" * 74 + "\n")


# =============================================================================
# 3. Synthetic placeholder phantom (LAST RESORT)
# =============================================================================
def make_phantom_volume(shape=(96, 140, 140)) -> tuple[np.ndarray, tuple]:
    """Generate a recognizable, organ-like ultrasound-ish phantom.

    A kidney-bean solid (ellipsoid minus a side indentation) with an internal
    low-intensity cavity, embedded in low-intensity background, plus multiplicative
    speckle to mimic ultrasound texture. After Otsu + largest-component + marching
    cubes this yields a smooth, clearly non-spherical, organ-like surface.

    Returns (uint16 volume (z,y,x), spacing (sz,sy,sx) in mm).
    """
    # NOTE: numpy's default RNG is fine here; this is offline data generation.
    rng = np.random.default_rng(7)
    z, y, x = shape
    zz, yy, xx = np.mgrid[0:z, 0:y, 0:x].astype(np.float32)
    cz, cy, cx = z / 2, y / 2, x / 2

    # Main ellipsoid (semi-axes in voxels).
    az, ay, ax = z * 0.34, y * 0.30, x * 0.38
    ellip = ((zz - cz) / az) ** 2 + ((yy - cy) / ay) ** 2 + ((xx - cx) / ax) ** 2
    body = ellip <= 1.0

    # Carve a concavity on one side to make a kidney-bean (recognizably organic).
    ind = (((zz - cz) / (z * 0.22)) ** 2
           + ((yy - cy) / (y * 0.22)) ** 2
           + ((xx - (cx + x * 0.30)) / (x * 0.26)) ** 2)
    body = body & (ind > 1.0)

    # Internal cavity (a chamber) — lower intensity, kept hollow.
    cav = (((zz - cz) / (z * 0.12)) ** 2
           + ((yy - cy) / (y * 0.12)) ** 2
           + ((xx - (cx - x * 0.10)) / (x * 0.12)) ** 2) <= 1.0

    vol = np.full(shape, 28.0, dtype=np.float32)         # dim background
    # Radial intensity falloff inside the body so the surface isn't a flat slab.
    falloff = np.clip(1.2 - 0.5 * ellip, 0.4, 1.0)
    vol[body] = 150.0 * falloff[body] + 40.0
    vol[cav & body] = 55.0                                # hollow chamber

    # --- Acoustic-shadow region (the honest-uncertainty showcase) -------------
    # Real ultrasound loses clarity behind shadowing structures. We dim the body
    # toward the background and add heavy speckle in the top z-slab, so its
    # boundary is fuzzy and ambiguous. The segmenter still captures it, but the
    # confidence proxy scores it LOW — which the narration then flags for re-scan.
    shadow = zz > (0.66 * z)
    shadow_body = shadow & body
    vol[shadow_body] = 78.0                               # weak, near-threshold signal

    # Ultrasound-like multiplicative speckle + extra speckle in the shadow slab.
    speckle = 1.0 + 0.28 * rng.standard_normal(shape).astype(np.float32)
    heavy = 1.0 + 0.55 * rng.standard_normal(shape).astype(np.float32)
    speckle = np.where(shadow, heavy, speckle)
    vol = vol * np.clip(speckle, 0.3, 2.0)
    vol = np.clip(vol, 0, 255)

    # Anisotropic spacing (mm) to demonstrate spacing preservation -> small organ.
    spacing = (0.6, 0.45, 0.45)  # (sz, sy, sx)
    return vol.astype(np.uint16), spacing


def write_dicom_series(volume: np.ndarray, spacing: tuple, out_dir: str) -> None:
    """Write a uint16 volume as a DICOM series (one .dcm per z-slice).

    We set the spatial tags (PixelSpacing, SliceThickness, ImageOrientationPatient,
    ImagePositionPatient) that SimpleITK's series reader needs to assemble a true
    3D volume with correct spacing — i.e. this exercises the REAL primary path.

    The series is loudly tagged SYNTHETIC PLACEHOLDER so it can never be mistaken
    for real patient data.
    """
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import (ExplicitVRLittleEndian, generate_uid,
                             SecondaryCaptureImageStorage)

    os.makedirs(out_dir, exist_ok=True)
    # Clear any stale slices from a prior run.
    for f in os.listdir(out_dir):
        if f.lower().endswith(".dcm"):
            os.remove(os.path.join(out_dir, f))

    sz, sy, sx = spacing
    nz, ny, nx = volume.shape
    study_uid = generate_uid()
    series_uid = generate_uid()

    for z in range(nz):
        ds = Dataset()
        # --- Loud synthetic markers ---
        ds.PatientName = "SYNTHETIC^PLACEHOLDER"
        ds.PatientID = "SYNTHETIC-PLACEHOLDER"
        ds.StudyDescription = "SYNTHETIC PLACEHOLDER - replace with real scan before demo"
        ds.SeriesDescription = "SYNTHETIC ultrasound phantom (NOT real)"
        ds.Modality = "US"

        ds.StudyInstanceUID = study_uid
        ds.SeriesInstanceUID = series_uid
        ds.SOPInstanceUID = generate_uid()
        ds.SOPClassUID = SecondaryCaptureImageStorage
        ds.SeriesNumber = 1
        ds.InstanceNumber = z + 1

        # Pixel module
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.Rows = ny
        ds.Columns = nx
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 0          # unsigned
        ds.PixelData = volume[z].tobytes()

        # Spatial module (what the series reader uses to build the 3D volume)
        ds.PixelSpacing = [float(sy), float(sx)]          # [row(y), col(x)]
        ds.SliceThickness = float(sz)
        ds.SpacingBetweenSlices = float(sz)
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.ImagePositionPatient = [0.0, 0.0, float(z * sz)]
        ds.FrameOfReferenceUID = study_uid

        # File meta + save
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = ds.SOPClassUID
        meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        meta.ImplementationClassUID = generate_uid()
        fds = pydicom.FileDataset(None, ds, file_meta=meta, preamble=b"\x00" * 128)
        fds.is_little_endian = True
        fds.is_implicit_VR = False
        fds.save_as(os.path.join(out_dir, f"slice_{z:04d}.dcm"))

    # Unmistakable sidecar flag.
    with open(os.path.join(out_dir, "SYNTHETIC_PLACEHOLDER.txt"), "w") as f:
        f.write("SYNTHETIC PLACEHOLDER ULTRASOUND PHANTOM.\n"
                "This is NOT real patient data. Replace data/sample with a real "
                "volumetric ultrasound before the judged demo.\n")
    print(f"Wrote {nz} synthetic DICOM slices to {out_dir}")


# =============================================================================
# Manifest
# =============================================================================
def write_manifest(path: str, input_type: str, anatomy_label: str,
                   is_synthetic: bool, note: str, modality: str = "auto") -> None:
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    manifest = {
        "path": path,
        "input_type": input_type,
        "anatomy_label": anatomy_label,
        "is_synthetic_placeholder": is_synthetic,
        "modality": modality,
        "note": note,
    }
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote manifest -> {MANIFEST}")
    print(json.dumps(manifest, indent=2))


def main() -> int:
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    os.makedirs(REAL_DIR, exist_ok=True)

    # 1. Real scan already provided?
    real = find_real_volume()
    if real is not None:
        path, input_type = real
        print(f"Found a REAL volume: {path} (input_type={input_type})")
        write_manifest(
            path=path, input_type=input_type,
            anatomy_label="a real 3D echocardiography / ultrasound volume",
            is_synthetic=False, modality="ultrasound",
            note="Real volumetric scan provided by the user in data/sample/real/.")
        return 0

    # 2. Best-effort auto-fetch (honest about registration walls).
    fetched = attempt_fetch_real_echo()
    if fetched is not None:
        path, input_type = fetched
        write_manifest(
            path=path, input_type=input_type,
            anatomy_label="a real 3D echocardiography / ultrasound volume",
            is_synthetic=False, modality="ultrasound",
            note=f"Real volume auto-fetched from {ECHO_VOLUME_URL_ENV}.")
        return 0

    # 3. No reliable programmatic fetch; tell the user exactly how to get one.
    print_real_data_instructions()

    # 4. Generate the clearly-labeled synthetic placeholder so the demo still runs.
    print(">>> Generating SYNTHETIC PLACEHOLDER phantom (last resort) <<<")
    try:
        import pydicom  # noqa: F401  (import here to give a clean error if missing)
    except Exception:
        print("ERROR: pydicom is required to write the phantom. "
              "Install deps: pip install -r requirements.txt", file=sys.stderr)
        return 1

    volume, spacing = make_phantom_volume()
    write_dicom_series(volume, spacing, PHANTOM_DIR)
    write_manifest(
        path=PHANTOM_DIR,
        input_type="dicom_series_dir",
        anatomy_label="a SYNTHETIC PLACEHOLDER phantom (organ-like model, NOT a real scan)",
        is_synthetic=True, modality="ultrasound",   # phantom is tagged US -> exercises the US path
        note="SYNTHETIC PLACEHOLDER — replace with a real scan before the demo.")
    print("\nDone. The /demo path will run on the synthetic placeholder until you "
          "drop a real scan into data/sample/real/ and re-run this script.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
