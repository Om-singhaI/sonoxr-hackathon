#!/usr/bin/env python3
"""TASK 3 — Build an unbreakable BACKUP demo clip.

Produces demo/backup_demo.mp4 (falls back to .gif if the MP4 codec is
unavailable): a short, looping turntable of the FROZEN golden model with the
narration + confidence overlaid. This is the absolute last resort if every live
layer (L1/L2/L3) fails on stage.

HONESTY: this is a RENDERED clip of the reconstructed model — it is NOT a screen
capture of the live app, and it is labeled as such in the video itself. For the
canonical screen recording of the real click-flow, see the manual steps printed
at the end (also in DEMO_RUNBOOK.md). There is no EF / beating heart in this
codebase, so none is shown.

    python scripts/record_demo.py
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import trimesh
import cv2

GOLDEN_GLB = os.path.join(ROOT, "demo", "golden", "model.glb")
GOLDEN_META = os.path.join(ROOT, "frontend", "golden", "golden_meta.json")
OUT_MP4 = os.path.join(ROOT, "demo", "backup_demo.mp4")
OUT_GIF = os.path.join(ROOT, "demo", "backup_demo.gif")

W = H = 640
FPS = 12
ROT_FRAMES = 120          # ~10s rotation
CARD_FRAMES = 18          # ~1.5s title / outro
TISSUE = np.array([0.86, 0.72, 0.63]); LIGHT = np.array([.4, .5, .8]); LIGHT /= np.linalg.norm(LIGHT)


def wrap(text, width=58):
    out, line = [], ""
    for w in (text or "").split():
        if len(line) + len(w) + 1 > width:
            out.append(line); line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(line)
    return out


def put_lines(img, lines, x, y, scale=0.5, color=(235, 240, 247), thick=1, dy=22):
    for i, ln in enumerate(lines):
        cv2.putText(img, ln, (x, y + i * dy), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (0, 0, 0), thick + 2, cv2.LINE_AA)        # outline for legibility
        cv2.putText(img, ln, (x, y + i * dy), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    color, thick, cv2.LINE_AA)
    return y + len(lines) * dy


def render_mesh_frames(meta):
    mesh = trimesh.load(GOLDEN_GLB, force="mesh")
    if len(mesh.faces) > 6000:
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=6000)
        except Exception:
            pass
    V = mesh.vertices
    xyz = np.column_stack([V[:, 2], V[:, 1], V[:, 0]])
    tris = xyz[mesh.faces]
    fn = mesh.face_normals
    shade = (0.4 + 0.6 * np.clip(fn @ LIGHT, 0, 1))[:, None]
    facecolors = np.clip(TISSUE[None, :] * shade, 0, 1)

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor="#070a0f")
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("#070a0f")
    pc = Poly3DCollection(tris, facecolors=facecolors, linewidths=0)
    ax.add_collection3d(pc)
    lo, hi = xyz.min(0), xyz.max(0); mid = (hi + lo) / 2; span = (hi - lo).max()
    ax.set_xlim(mid[0]-span/2, mid[0]+span/2); ax.set_ylim(mid[1]-span/2, mid[1]+span/2)
    ax.set_zlim(mid[2]-span/2, mid[2]+span/2); ax.set_box_aspect((1, 1, 1)); ax.set_axis_off()

    # Overlay text prepared once.
    conf = meta.get("confidence", {}) or {}
    anat = meta.get("anatomy_label", "Reconstruction")
    ovl = (f"confidence {conf.get('overall')} ({conf.get('overall_label')})"
           if conf.get("overall") is not None else "")
    low = conf.get("low_confidence_regions") or []
    rescan = (f"Re-scan recommended: {', '.join(low)}" if low else "")
    narr_lines = wrap(meta.get("narration", ""), 60)[:4]

    frames = []
    for i in range(ROT_FRAMES):
        ax.view_init(elev=18, azim=(360 * i / ROT_FRAMES) + 30)
        fig.canvas.draw()
        rgba = np.asarray(fig.canvas.buffer_rgba())
        bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        # top banner (honesty label)
        cv2.rectangle(bgr, (0, 0), (W, 26), (20, 25, 33), -1)
        put_lines(bgr, ["SonoXR / EchoAR  —  RENDERED BACKUP CLIP (not a live capture)"],
                  10, 18, 0.45, (147, 160, 178))
        # bottom info panel
        cv2.rectangle(bgr, (0, H - 150), (W, H), (12, 16, 22), -1)
        y = put_lines(bgr, [anat], 12, H - 124, 0.62, (238, 243, 250), 2, 26)
        if ovl:
            put_lines(bgr, [ovl], 12, y - 4, 0.5, (104, 196, 138))
        y2 = put_lines(bgr, narr_lines, 12, H - 70, 0.42, (219, 228, 239), 1, 16)
        if rescan:
            put_lines(bgr, ["⚠ " + rescan], 12, H - 10, 0.46, (90, 110, 236))
        frames.append(bgr)
    plt.close(fig)
    return frames, anat


def card(text_lines, sub=None):
    img = np.full((H, W, 3), (10, 14, 19), np.uint8)
    put_lines(img, text_lines, 40, H // 2 - 10, 0.95, (238, 243, 250), 2, 40)
    if sub:
        put_lines(img, sub, 40, H // 2 + 70, 0.5, (147, 160, 178), 1, 24)
    return img


def main() -> int:
    if not os.path.exists(GOLDEN_GLB):
        print("ERROR: no frozen golden model. Run scripts/freeze_golden.py first.",
              file=sys.stderr)
        return 1
    meta = json.load(open(GOLDEN_META)) if os.path.exists(GOLDEN_META) else {}

    print("Rendering backup clip frames…")
    rot, anat = render_mesh_frames(meta)
    intro = [card(["SonoXR / EchoAR", "AR ultrasound reconstruction"],
                  ["Backup demo clip — last resort if the live demo fails"])] * CARD_FRAMES
    outro = [card(["View in AR on a phone", "for the live experience"],
                  ["Reconstruction + uncertainty narration (no EF in this build)"])] * CARD_FRAMES
    frames = intro + rot + outro
    dur = len(frames) / FPS
    print(f"{len(frames)} frames (~{dur:.0f}s @ {FPS}fps)")

    # Write MP4 via OpenCV (no ffmpeg binary needed; uses the mp4v codec).
    os.makedirs(os.path.dirname(OUT_MP4), exist_ok=True)
    writer = cv2.VideoWriter(OUT_MP4, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    ok = writer.isOpened()
    if ok:
        for f in frames:
            writer.write(f)
        writer.release()
        ok = os.path.exists(OUT_MP4) and os.path.getsize(OUT_MP4) > 1000
    if ok:
        print(f"Wrote {OUT_MP4} ({os.path.getsize(OUT_MP4)//1024} KB)")
    else:
        # Fallback: animated GIF via Pillow.
        from PIL import Image
        print("MP4 codec unavailable; writing GIF fallback…")
        imgs = [Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)) for f in frames]
        imgs[0].save(OUT_GIF, save_all=True, append_images=imgs[1:],
                     duration=int(1000 / FPS), loop=0)
        print(f"Wrote {OUT_GIF} ({os.path.getsize(OUT_GIF)//1024} KB)")

    print("\n--- Canonical backup: record the REAL click-flow (do this on your machine) ---")
    print(" macOS:  Cmd+Shift+5 -> Record Selected Portion -> capture the browser, then:")
    print("   1) press Run Demo (model appears),  2) drag to orbit,")
    print("   3) point out the confidence + re-scan note + narration,")
    print("   4) on a phone, tap View in AR.   Keep it 60-90s.")
    print(" Save it as demo/backup_demo.mp4 (overwriting this rendered placeholder).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
