#!/usr/bin/env python3
"""Iteration 5 / step 1 — KNOW the EchoNet 3d-echo format before coding anything.

Inspects the public dataset and PRINTS, for representative files: the member list
(so we see the Person A/B/C/D grouping), and for one loaded file its FORMAT, shape,
dtype, voxel spacing, and dimensionality (is it XYZ+T 4D?). We do NOT assume.

Data: https://github.com/echonet/3d-echo/releases/download/v1.0/dataset.zip
(29 real 3D echocardiogram videos; cite EchoNet 3d-echo per its license.)

Two modes (auto-selected by free disk):
  * FULL    — download dataset.zip (~1.1 GB), unzip, inspect. Needs lots of disk.
  * REMOTE  — when disk is tight: read the zip's central directory over HTTP range
              requests (no full download), list members, and extract ONE volume
              member to a temp file to inspect it, then clean up. ~tens of MB.

    python scripts/inspect_echo.py            # auto
    python scripts/inspect_echo.py --full     # force full download
    python scripts/inspect_echo.py --remote   # force remote one-member inspect
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import urllib.request
import zipfile

URL = "https://github.com/echonet/3d-echo/releases/download/v1.0/dataset.zip"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, "data", "sample", "echonet_src")
TMP = "/tmp/echonet_inspect"
VOL_EXT = (".nii", ".nii.gz", ".mha", ".mhd", ".nrrd", ".dcm", ".vtk", ".raw",
           ".mat", ".npy", ".npz", ".seq")
# Cap on a single member we'll pull to disk for inspection (free-disk safety).
MAX_MEMBER_MB = 170


# =============================================================================
# HTTP range-backed file object so zipfile can read a remote zip w/o full download
# =============================================================================
class HTTPRangeReader(io.RawIOBase):
    def __init__(self, url):
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0",
                                                   "User-Agent": "SonoXR/5"})
        r = urllib.request.urlopen(req, timeout=60)
        self.url = r.geturl()                       # resolved (presigned) URL
        cr = r.headers.get("Content-Range")
        self.size = int(cr.split("/")[-1]) if cr else int(r.headers["Content-Length"])
        r.read()
        self.pos = 0

    def seekable(self): return True
    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos
    def tell(self): return self.pos

    def readinto(self, b):
        n = len(b)
        if n == 0 or self.pos >= self.size:
            return 0
        end = min(self.pos + n, self.size) - 1
        req = urllib.request.Request(self.url, headers={
            "Range": f"bytes={self.pos}-{end}", "User-Agent": "SonoXR/5"})
        data = urllib.request.urlopen(req, timeout=180).read()
        b[:len(data)] = data
        self.pos += len(data)
        return len(data)


# =============================================================================
# Inspection of one extracted file (format / shape / dtype / spacing / ndim)
# =============================================================================
def inspect_file(path: str) -> None:
    name = os.path.basename(path)
    low = name.lower()
    print(f"\n--- inspecting member: {name} ({os.path.getsize(path)/1e6:.1f} MB on disk) ---")
    with open(path, "rb") as f:
        head = f.read(16)
    print(f"first 16 bytes: {head!r}")

    # .mat (MATLAB) — common for echo research data
    if low.endswith(".mat"):
        try:
            import scipy.io as sio
            m = sio.loadmat(path)
            keys = [k for k in m if not k.startswith("__")]
            print("format: MATLAB .mat  | variables:")
            for k in keys:
                v = m[k]
                print(f"   {k}: shape={getattr(v,'shape',None)} dtype={getattr(v,'dtype',None)}")
            return
        except Exception as e:
            print(f"scipy.io.loadmat failed ({e}); may be v7.3/HDF5 — try h5py.")
            try:
                import h5py
                with h5py.File(path, "r") as h:
                    print("format: MATLAB v7.3 (HDF5) | datasets:")
                    h.visititems(lambda n, o: print(f"   {n}: shape={getattr(o,'shape',None)} dtype={getattr(o,'dtype',None)}") if hasattr(o, "shape") else None)
            except Exception as e2:
                print(f"h5py also failed ({e2}).")
            return

    if low.endswith(".npy") or low.endswith(".npz"):
        import numpy as np
        obj = np.load(path, allow_pickle=True)
        if low.endswith(".npz"):
            for k in obj.files:
                a = obj[k]; print(f"   npz[{k}]: shape={a.shape} dtype={a.dtype}")
        else:
            print(f"format: NumPy .npy  shape={obj.shape} dtype={obj.dtype} ndim={obj.ndim}")
        return

    # Medical volume formats via SimpleITK
    try:
        import SimpleITK as sitk
        img = sitk.ReadImage(path)
        sz = img.GetSize()            # (x,y,z[,t])
        sp = img.GetSpacing()
        print(f"format: read by SimpleITK")
        print(f"  size (x,y,z[,t]) = {sz}   -> dimension = {img.GetDimension()}D")
        print(f"  spacing          = {tuple(round(s,4) for s in sp)}")
        print(f"  pixel type       = {img.GetPixelIDTypeAsString()}")
        print(f"  4D (XYZ+T)?      = {img.GetDimension() == 4}")
        if img.HasMetaDataKey("0008|0060"):
            print(f"  DICOM modality   = {img.GetMetaData('0008|0060')}")
        return
    except Exception as e:
        print(f"SimpleITK could not read it ({e}).")

    print("format: UNRECOGNIZED by SimpleITK/scipy/numpy — inspect manually. "
          "Header bytes above may identify it.")


def summarize_members(infos) -> None:
    print(f"\n=== {len(infos)} members ===")
    total = 0
    for i in infos:
        total += i.file_size
        print(f"  {i.filename}  ({i.file_size/1e6:.1f} MB)")
    print(f"total uncompressed: {total/1e6:.0f} MB")
    # naive person grouping by leading token of the path
    from collections import Counter
    groups = Counter()
    for i in infos:
        base = i.filename.strip("/").split("/")[0]
        groups[base] += 1
    print("top-level grouping:", dict(groups))


def pick_volume_member(infos):
    """Smallest data-looking member under the size cap (so it fits on a tight disk)."""
    cands = [i for i in infos if not i.is_dir()
             and i.file_size > 0
             and i.file_size < MAX_MEMBER_MB * 1e6
             and (i.filename.lower().endswith(VOL_EXT) or "." in os.path.basename(i.filename))]
    # prefer recognized volume extensions; among those, smallest
    vols = [i for i in cands if i.filename.lower().endswith(VOL_EXT)]
    pool = vols or cands
    return min(pool, key=lambda i: i.file_size) if pool else None


def remote_inspect():
    print(f"REMOTE mode — reading the zip's central directory over HTTP range "
          f"(no {os.path.getsize and ''}full download).")
    reader = HTTPRangeReader(URL)
    print(f"zip total size: {reader.size/1e6:.0f} MB")
    zf = zipfile.ZipFile(reader)
    infos = zf.infolist()
    summarize_members(infos)

    target = pick_volume_member(infos)
    if target is None:
        print("\nNo member under the size cap to inspect; printing names only.")
        return
    os.makedirs(TMP, exist_ok=True)
    out = os.path.join(TMP, os.path.basename(target.filename))
    print(f"\nExtracting ONE member for inspection: {target.filename} "
          f"({target.file_size/1e6:.1f} MB)…")
    try:
        with zf.open(target) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        inspect_file(out)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)   # reclaim disk immediately


def full_inspect():
    os.makedirs(CACHE, exist_ok=True)
    zip_path = os.path.join(CACHE, "dataset.zip")
    if not os.path.exists(zip_path):
        print(f"Downloading {URL} (~1.1 GB)…")
        urllib.request.urlretrieve(URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        summarize_members(infos)
        zf.extractall(CACHE)
    # inspect a representative file of each recognized type
    seen_ext = set()
    for root, _d, files in os.walk(CACHE):
        for fn in sorted(files):
            ext = os.path.splitext(fn.lower())[1]
            if ext in (".zip",) or ext in seen_ext:
                continue
            seen_ext.add(ext)
            inspect_file(os.path.join(root, fn))


def free_gb(path=ROOT) -> float:
    st = shutil.disk_usage(path)
    return st.free / 1e9


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--auto"
    print(f"free disk: {free_gb():.2f} GB")
    if mode == "--full" or (mode == "--auto" and free_gb() > 3.0):
        full_inspect()
    else:
        if mode == "--auto":
            print("(<3 GB free -> REMOTE one-member inspection to avoid the 1.1 GB download)")
        remote_inspect()
    print("\nDONE. Use these findings to write the loader (do not assume).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
