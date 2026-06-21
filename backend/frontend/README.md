# SonoXR / EchoAR — self-contained AR page

`ar.html` is a single static file (no build step). It shows the reconstructed
`.glb`, the narration, and the per-region **confidence** (chips + a "re-scan
recommended" banner), and launches **AR** on a phone. It is the demo's wow surface
and its last-resort safety net — it works even with the backend down.

> This build shows volumetric reconstruction + uncertainty narration. There is no
> ejection fraction / beating heart in this codebase (not built) — the page does
> not display one.

## Prerequisite: freeze the golden artifact (once)

```bash
python scripts/freeze_golden.py
```
This writes `frontend/golden/model.glb` + `golden_meta.json` (and the backend's
`demo/golden/` cache). The AR page loads these **instantly and offline**.

## The triple-layer behavior (TASK 2)

| Layer | When | What the page shows |
|---|---|---|
| **L3 (instant/offline)** | always, on load + on Run Demo | the **bundled** `./golden/model.glb` + narration/confidence — **no backend needed** |
| **L1 LIVE** | backend reachable, recompute ok | swaps in the freshly recomputed model + narration |
| **L2 CACHED** | backend reachable but recompute slow/errors | server serves its frozen `/golden/model.glb` |

So pressing **Run Demo** shows the model in <1s from the bundle, then quietly
upgrades to the live result if the backend answers. If the backend is unreachable,
it simply stays on the bundle — no error wall, no blank screen.

`model-viewer` is **vendored** at `frontend/vendor/model-viewer.min.js`, so the
3D/AR view works with no internet (CDN is only a fallback).

## Run it

```bash
# Backend (optional for L1/L2; not needed for L3):
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Serve the page (from repo root):
python -m http.server 5173
# open http://localhost:5173/frontend/ar.html
```

## The live AR moment (phone, same Wi-Fi)

1. Laptop IP: `ipconfig getifaddr en0` (macOS) / `hostname -I` (Linux).
2. On the phone open `http://<laptop-ip>:5173/frontend/ar.html`.
3. In **backend settings** set `http://<laptop-ip>:8000` (only if you want L1/L2).
4. Tap **Run Demo** → orbit the model → tap **View in AR** to place it in the room.

> Even with **no backend and no Wi-Fi**, opening `ar.html` from a local static
> server shows the bundled golden model + narration. That is layer L3.

---

## Real 2D beating-heart demo — `echo.html` (iteration 5)

`echo.html` plays a **real 2D echocardiogram** (a beating heart) from the public
**EchoNet 3d-echo** dataset, with the real cardiac-rhythm curve, honest narration,
and capture-confidence. It is **fully offline** — it loads only the bundled
`frontend/golden_echo/` artifact (no backend, inherently the L3 layer).

```bash
python scripts/build_echo_demo.py     # builds frontend/golden_echo/{heart.mp4,curve.png,meta.json}
python -m http.server 5173            # then open http://localhost:5173/frontend/echo.html
```

> **Honest scope:** the EchoNet `dataset.zip` (v1.0) is **2D cine (2D + time), not 3D
> volumes** (verified from the DICOM tags). So this is a faithful 2D player — the
> motion/rhythm and ED/ES *timing* are real; we do **not** report an LV trace,
> fractional-area-change, or ejection fraction (those need a trained model). Cite
> EchoNet 3d-echo (https://github.com/echonet/3d-echo) per its license.
