"""Iteration 6 — Real 3D LV from CAMUS 2D apical masks via Simpson's biplane.

This is HONEST 3D from real clinical geometry — NOT a fabricated depth axis. From
the expert _gt masks (label 1 = LV cavity) of the apical 2-chamber and 4-chamber
views, at end-diastole (ED) and end-systole (ES), we:

  1. extract the LV-cavity contour per view/phase;
  2. find the LV long axis (apex -> mitral/LA-side base midpoint);
  3. resample N short-axis levels along the long axis (method of discs), taking the
     4CH diameter (D4) and 2CH diameter (D2) at each level;
  4. stack ELLIPTICAL discs (semi-axes D4/2, D2/2) into a smooth 3D LV surface.

Volume (Simpson's biplane, the clinical formula, DIAMETERS):
      V = (pi/4) * sum_i ( D4_i * D2_i * h ),   h = long-axis length / N
EF = (EDV - ESV) / EDV * 100.

CAMUS ships a reference EF per patient (Info_*.cfg) — we validate against it.
Cite: Leclerc et al., IEEE TMI 2019 (doi:10.1109/TMI.2019.2900516).
"""

from __future__ import annotations

import os
import re

import numpy as np
import SimpleITK as sitk
from scipy import ndimage as ndi

LV_CAVITY, MYO, LA = 1, 2, 3        # CAMUS mask labels
N_DISCS = 20                        # Simpson's method of discs (clinical standard)
RING_K = 48                         # vertices per short-axis ellipse


# =============================================================================
# Mask -> contour geometry
# =============================================================================
def _read_label(gt_path: str):
    img = sitk.ReadImage(gt_path)
    arr = sitk.GetArrayFromImage(img)          # (H, W)
    spacing_mm = float(img.GetSpacing()[0])    # isotropic in CAMUS
    return arr, spacing_mm


def _long_axis(cav: np.ndarray, la: np.ndarray):
    """Return (apex_xy, base_xy). Base = LV-cavity midpoint at the mitral plane
    (where the cavity meets the left atrium); apex = farthest cavity point from it."""
    ys, xs = np.where(cav)
    pts = np.column_stack([xs, ys]).astype(float)
    la_dil = ndi.binary_dilation(la, iterations=4)
    border = cav & la_dil
    if border.sum() > 5:
        by, bx = np.where(border)
        base = np.array([bx.mean(), by.mean()])
    else:                                       # fallback: cavity point nearest LA centroid
        ly, lx = np.where(la)
        lac = np.array([lx.mean(), ly.mean()]) if lx.size else pts.mean(0)
        base = pts[np.argmin(((pts - lac) ** 2).sum(1))]
    apex = pts[np.argmax(((pts - base) ** 2).sum(1))]
    return apex, base


def _half_widths(cav: np.ndarray, apex, base, n: int = N_DISCS):
    """Half-width (radius) of the cavity at n evenly spaced levels apex->base,
    plus the long-axis length L (px)."""
    u = base - apex
    L = float(np.linalg.norm(u))
    if L < 1e-6:
        return np.zeros(n), 1.0
    u = u / L
    v = np.array([-u[1], u[0]])                 # perpendicular (short-axis direction)
    H, W = cav.shape
    ss = np.arange(-400, 400, 0.5)
    hw = np.zeros(n)
    for i in range(n):
        P = apex + u * (((i + 0.5) / n) * L)
        s = P[None, :] + ss[:, None] * v[None, :]
        xi = np.round(s[:, 0]).astype(int); yi = np.round(s[:, 1]).astype(int)
        ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
        ins = np.zeros(len(ss), bool); ins[ok] = cav[yi[ok], xi[ok]]
        if ins.any():
            hw[i] = (ss[ins].max() - ss[ins].min()) / 2.0
    return hw, L


# =============================================================================
# Disc stack -> mesh (consistent topology across phases for morphing)
# =============================================================================
def build_lv_mesh(a_cm: np.ndarray, b_cm: np.ndarray, h_cm: float, k: int = RING_K):
    """Elliptical disc-stack surface. Column 0 is the long axis (apex at 0).
    Topology is fixed by (len(a_cm), k) so ED and ES meshes correspond 1:1."""
    n = len(a_cm)
    th = 2 * np.pi * np.arange(k) / k
    cos, sin = np.cos(th), np.sin(th)
    V = []
    for i in range(n):
        z = (i + 0.5) * h_cm
        for kk in range(k):
            V.append([z, b_cm[i] * sin[kk], a_cm[i] * cos[kk]])
    V = np.array(V, dtype=np.float64)
    F = []
    for i in range(n - 1):
        for kk in range(k):
            A = i * k + kk; B = i * k + (kk + 1) % k
            C = (i + 1) * k + kk; D = (i + 1) * k + (kk + 1) % k
            F += [[A, B, D], [A, D, C]]
    apex_i = len(V); V = np.vstack([V, [0.0, 0.0, 0.0]])
    base_i = len(V); V = np.vstack([V, [n * h_cm, 0.0, 0.0]])
    for kk in range(k):
        F.append([apex_i, (kk + 1) % k, kk])                         # apex cap
        F.append([base_i, (n - 1) * k + kk, (n - 1) * k + (kk + 1) % k])  # base cap
    return V, np.array(F, dtype=np.int64)


def simpson_volume_mL(a_cm: np.ndarray, b_cm: np.ndarray, h_cm: float) -> float:
    """Clinical Simpson's biplane with DIAMETERS: V = (pi/4) Σ D4·D2·h, D=2·half-width."""
    d4, d2 = 2 * a_cm, 2 * b_cm
    return float((np.pi / 4.0) * np.sum(d4 * d2 * h_cm))


# =============================================================================
# Per-phase + per-patient reconstruction
# =============================================================================
def reconstruct_phase(patient_dir: str, pid: str, phase: str, n: int = N_DISCS) -> dict:
    cav4, sp = _read_label(os.path.join(patient_dir, f"{pid}_4CH_{phase}_gt.nii.gz"))[0:2]
    la4 = (cav4 == LA); c4 = (cav4 == LV_CAVITY)
    m2, _ = _read_label(os.path.join(patient_dir, f"{pid}_2CH_{phase}_gt.nii.gz"))
    la2 = (m2 == LA); c2 = (m2 == LV_CAVITY)

    a4, ba4 = _long_axis(c4, la4); a2, ba2 = _long_axis(c2, la2)
    hw4, L4 = _half_widths(c4, a4, ba4, n)
    hw2, L2 = _half_widths(c2, a2, ba2, n)
    cmpx = sp * 0.1                                  # mm -> cm
    a_cm = hw4 * cmpx                                # 4CH half-widths (cm)
    b_cm = hw2 * cmpx                                # 2CH half-widths (cm)
    h_cm = (0.5 * (L4 + L2) / n) * cmpx              # disc height from mean long axis
    vol = simpson_volume_mL(a_cm, b_cm, h_cm)
    verts, faces = build_lv_mesh(a_cm, b_cm, h_cm)
    return {"phase": phase, "a_cm": a_cm, "b_cm": b_cm, "h_cm": h_cm,
            "volume_mL": vol, "verts": verts, "faces": faces,
            "L4_px": L4, "L2_px": L2, "spacing_mm": sp}


def read_reference_ef(patient_dir: str) -> dict:
    """CAMUS reference EF + image quality from Info_{2CH,4CH}.cfg, if present."""
    out = {}
    for view in ("2CH", "4CH"):
        p = os.path.join(patient_dir, f"Info_{view}.cfg")
        if os.path.exists(p):
            d = {}
            for line in open(p):
                if ":" in line:
                    key, _, val = line.partition(":")
                    d[key.strip()] = val.strip()
            out[view] = d
    ef = None; quality = None
    for view in ("4CH", "2CH"):
        if view in out:
            try:
                ef = float(out[view].get("EF")) if out[view].get("EF") else ef
            except Exception:
                pass
            quality = out[view].get("ImageQuality", quality)
    return {"reference_ef": ef, "image_quality": quality, "raw": out}


def reconstruct_patient(patient_dir: str, n: int = N_DISCS) -> dict:
    pid = os.path.basename(patient_dir.rstrip("/"))
    ed = reconstruct_phase(patient_dir, pid, "ED", n)
    es = reconstruct_phase(patient_dir, pid, "ES", n)
    edv, esv = ed["volume_mL"], es["volume_mL"]
    ef = 100.0 * (edv - esv) / edv if edv > 0 else 0.0
    ref = read_reference_ef(patient_dir)
    return {"patient": pid, "ed": ed, "es": es,
            "EDV_mL": round(edv, 1), "ESV_mL": round(esv, 1), "EF_pct": round(ef, 1),
            "reference_ef": ref["reference_ef"], "image_quality": ref["image_quality"],
            "n_discs": n, "spacing_mm": ed["spacing_mm"]}


# =============================================================================
# Beating glb (morph-target animation: ED <-> ES, looping) via pygltflib
# =============================================================================
def write_beating_glb(ed_verts, es_verts, faces, out_path: str,
                      cm_to_m: float = 0.01) -> bool:
    """Author a glTF (.glb) whose single mesh morphs ED<->ES on a looping animation.
    ED and ES MUST share topology (they do — build_lv_mesh is deterministic).
    Returns True on success; False if pygltflib is unavailable (caller falls back)."""
    try:
        import pygltflib as g
    except Exception:
        return False
    import trimesh

    ed = np.asarray(ed_verts, np.float64); es = np.asarray(es_verts, np.float64)
    # center both by the SAME translation; scale cm -> m so AR is life-size (~9 cm)
    center = ed.mean(0)
    ed_m = ((ed - center) * cm_to_m).astype(np.float32)
    es_m = ((es - center) * cm_to_m).astype(np.float32)
    tri_ed = trimesh.Trimesh(ed_m, faces, process=False); tri_ed.fix_normals()
    tri_es = trimesh.Trimesh(es_m, faces, process=False); tri_es.fix_normals()
    n_ed = tri_ed.vertex_normals.astype(np.float32)
    n_es = tri_es.vertex_normals.astype(np.float32)
    idx = np.asarray(faces, np.uint32).reshape(-1)
    dpos = (es_m - ed_m).astype(np.float32)
    dnrm = (n_es - n_ed).astype(np.float32)
    times = np.array([0.0, 0.45, 0.9], np.float32)        # ED -> ES -> ED, ~0.9 s loop
    weights = np.array([0.0, 1.0, 0.0], np.float32)

    blobs = [idx.tobytes(), ed_m.tobytes(), n_ed.tobytes(),
             dpos.tobytes(), dnrm.tobytes(), times.tobytes(), weights.tobytes()]
    # pad each to 4 bytes
    data = b""; offsets = []
    for b in blobs:
        offsets.append(len(data)); data += b + b"\x00" * ((4 - len(b) % 4) % 4)

    def acc(bv, ctype, count, atype, mn=None, mx=None):
        a = g.Accessor(bufferView=bv, componentType=ctype, count=count, type=atype)
        if mn is not None: a.min = mn; a.max = mx
        return a

    gltf = g.GLTF2()
    gltf.buffers = [g.Buffer(byteLength=len(data))]
    bvs, sizes = [], [b for b in blobs]
    targets = [g.ARRAY_BUFFER, g.ARRAY_BUFFER, g.ARRAY_BUFFER, g.ARRAY_BUFFER,
               g.ARRAY_BUFFER, None, None]
    eltarget = [g.ELEMENT_ARRAY_BUFFER, None, None, None, None, None, None]
    for i, b in enumerate(blobs):
        bv = g.BufferView(buffer=0, byteOffset=offsets[i], byteLength=len(b))
        if i == 0:
            bv.target = g.ELEMENT_ARRAY_BUFFER
        elif i in (1, 2, 3, 4):
            bv.target = g.ARRAY_BUFFER
        bvs.append(bv)
    gltf.bufferViews = bvs
    nv = len(ed_m)
    gltf.accessors = [
        acc(0, g.UNSIGNED_INT, len(idx), g.SCALAR),                                   # 0 indices
        acc(1, g.FLOAT, nv, g.VEC3, ed_m.min(0).tolist(), ed_m.max(0).tolist()),      # 1 POSITION
        acc(2, g.FLOAT, nv, g.VEC3),                                                  # 2 NORMAL
        acc(3, g.FLOAT, nv, g.VEC3, dpos.min(0).tolist(), dpos.max(0).tolist()),      # 3 dPOSITION
        acc(4, g.FLOAT, nv, g.VEC3),                                                  # 4 dNORMAL
        acc(5, g.FLOAT, len(times), g.SCALAR, [float(times.min())], [float(times.max())]),  # 5 anim time
        acc(6, g.FLOAT, len(weights), g.SCALAR),                                      # 6 anim weights
    ]
    prim = g.Primitive(attributes=g.Attributes(POSITION=1, NORMAL=2),
                       indices=0, targets=[{"POSITION": 3, "NORMAL": 4}])
    gltf.meshes = [g.Mesh(primitives=[prim], weights=[0.0])]
    gltf.nodes = [g.Node(mesh=0)]
    gltf.scenes = [g.Scene(nodes=[0])]; gltf.scene = 0
    sampler = g.AnimationSampler(input=5, output=6, interpolation="LINEAR")
    channel = g.AnimationChannel(sampler=0,
                                 target=g.AnimationChannelTarget(node=0, path="weights"))
    gltf.animations = [g.Animation(samplers=[sampler], channels=[channel], name="beat")]
    gltf.set_binary_blob(data)
    gltf.save_binary(out_path)
    return True
