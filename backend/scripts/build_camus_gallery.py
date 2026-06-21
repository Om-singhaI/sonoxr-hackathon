#!/usr/bin/env python3
"""Render a thumbnail for every CAMUS patient and build a scrollable gallery HTML.

Outputs:
  preview/gallery/patientXXXX.png   — single front-view thumbnail (200×250 px)
  preview/camus_gallery.html        — searchable gallery, EF colour-coded

    python scripts/build_camus_gallery.py
"""

from __future__ import annotations

import csv
import glob
import os
import sys
import time
import traceback

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app import camus_biplane as cb

DB          = os.path.join(ROOT, "data", "database_nifti")
RESULTS_CSV = os.path.join(ROOT, "data", "camus_all_results.csv")
GALLERY_DIR = os.path.join(ROOT, "preview", "gallery")
GALLERY_HTML= os.path.join(ROOT, "preview", "camus_gallery.html")

TISSUE = np.array([0.86, 0.72, 0.63])
LIGHT  = np.array([0.4, 0.5, 0.8]); LIGHT /= np.linalg.norm(LIGHT)


def _shade(fn):
    lit = np.clip(fn @ LIGHT, 0, 1)
    return np.clip(TISSUE[None,:] * (0.35 + 0.65 * lit)[:,None], 0, 1)


def render_thumbnail(verts, faces, out_path, elev=18, azim=200):
    """Single-view 200×250 px thumbnail."""
    V  = np.asarray(verts)
    # reorient: long-axis (col-0) becomes Z (vertical in plot)
    xyz = np.column_stack([V[:,2], V[:,1], V[:,0]])
    tris = xyz[np.asarray(faces)]
    fn_raw = np.cross(tris[:,1]-tris[:,0], tris[:,2]-tris[:,0])
    norms  = fn_raw / (np.linalg.norm(fn_raw, axis=1, keepdims=True) + 1e-8)
    colors = _shade(norms)

    fig = plt.figure(figsize=(2, 2.5), facecolor="#0b0e13")
    ax  = fig.add_axes([0,0,1,1], projection="3d", facecolor="#0b0e13")
    pc  = Poly3DCollection(tris, facecolors=colors, linewidths=0, antialiased=False)
    ax.add_collection3d(pc)
    lo, hi = xyz.min(0), xyz.max(0)
    mid = (lo + hi) / 2; span = (hi - lo).max() * 0.55
    ax.set_xlim(mid[0]-span, mid[0]+span)
    ax.set_ylim(mid[1]-span, mid[1]+span)
    ax.set_zlim(mid[2]-span, mid[2]+span)
    ax.set_box_aspect((1,1,1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.savefig(out_path, dpi=100, facecolor="#0b0e13", bbox_inches="tight", pad_inches=0)
    plt.close(fig)


def ef_color(ef):
    if ef < 35:   return "#ec5b50"   # red — severe
    if ef < 50:   return "#f5972b"   # amber — reduced
    if ef <= 65:  return "#43c08a"   # green — normal
    return "#5b9dff"                 # blue — high


def ef_label(ef):
    if ef < 35:  return "severe"
    if ef < 50:  return "reduced"
    if ef <= 65: return "normal"
    return "high"


def build_gallery_html(cards):
    """cards: list of dicts with keys: pid, ef, edv, esv, ref_ef, quality, thumb, phys"""
    items = []
    for c in cards:
        if not c["phys"]:
            color, badge = "#666", "degenerate"
            ef_str = f"EF {c['ef']}%"
        else:
            color = ef_color(c["ef"])
            badge = ef_label(c["ef"])
            ef_str = f"EF {c['ef']}%"
        ref_str = f"ref {c['ref_ef']}%" if c["ref_ef"] else ""
        img_path = f"gallery/{c['pid']}.png"
        items.append(f"""
  <div class="card" data-ef="{c['ef']}" data-pid="{c['pid']}"
       data-quality="{c['quality']}" data-badge="{badge}">
    <img src="{img_path}" alt="{c['pid']}" loading="lazy">
    <div class="info">
      <span class="pid">{c['pid'].replace('patient','#')}</span>
      <span class="ef" style="color:{color}">{ef_str}</span>
      <span class="sub">{ref_str}</span>
      <span class="sub">{c['quality'] or ''}</span>
    </div>
  </div>""")

    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SonoXR — CAMUS 500-patient LV gallery</title>
<style>
  :root{--bg:#0b0e13;--card:#151b25;--ink:#eef3fa;--muted:#93a0b2;
        --green:#43c08a;--amber:#f5972b;--red:#ec5b50;--blue:#5b9dff;}
  *{box-sizing:border-box;}
  html,body{margin:0;background:var(--bg);color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
  header{padding:16px 20px 10px;border-bottom:1px solid #1e2530;}
  h1{margin:0 0 4px;font-size:18px;}
  .sub-h{font-size:12px;color:var(--muted);}
  .controls{display:flex;gap:10px;flex-wrap:wrap;padding:10px 20px;
    border-bottom:1px solid #1e2530;align-items:center;}
  input[type=text]{background:#151b25;color:var(--ink);border:1px solid #2a3340;
    border-radius:8px;padding:6px 10px;font-size:13px;width:180px;}
  select{background:#151b25;color:var(--ink);border:1px solid #2a3340;
    border-radius:8px;padding:6px 10px;font-size:13px;}
  .count{font-size:12px;color:var(--muted);margin-left:auto;}
  .legend{display:flex;gap:12px;flex-wrap:wrap;padding:8px 20px;
    border-bottom:1px solid #1e2530;font-size:12px;}
  .dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:4px;}
  #grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));
    gap:10px;padding:14px 20px;}
  .card{background:var(--card);border-radius:10px;overflow:hidden;
    border:1px solid #1e2530;cursor:default;transition:border-color .15s;}
  .card:hover{border-color:#2a3340;}
  .card img{width:100%;display:block;aspect-ratio:4/5;object-fit:cover;
    background:#070a0f;}
  .info{padding:6px 8px 8px;}
  .pid{display:block;font-size:11px;color:var(--muted);margin-bottom:2px;}
  .ef{display:block;font-size:15px;font-weight:800;line-height:1.1;}
  .sub{display:block;font-size:10.5px;color:var(--muted);margin-top:1px;}
  .card[data-badge="degenerate"]{opacity:0.45;}
  .hidden{display:none!important;}
  a{color:var(--blue);}
</style>
</head>
<body>
<header>
  <h1>CAMUS — all 500 patients · Simpson's biplane 3D LV</h1>
  <div class="sub-h">
    3D LV reconstructed from real expert-annotated 2D apical views (2CH+4CH) via
    Simpson's biplane method of discs — the clinical standard.
    NOT a 3D-echo volume acquisition.
    <br>Data: S. Leclerc et al., IEEE TMI 38(9):2198–2210, 2019.
    doi:10.1109/TMI.2019.2900516
  </div>
</header>
<div class="legend">
  <span><span class="dot" style="background:#ec5b50"></span>EF &lt;35% severe</span>
  <span><span class="dot" style="background:#f5972b"></span>EF 35–49% reduced</span>
  <span><span class="dot" style="background:#43c08a"></span>EF 50–65% normal</span>
  <span><span class="dot" style="background:#5b9dff"></span>EF &gt;65% high</span>
  <span><span class="dot" style="background:#444"></span>degenerate (out-of-range)</span>
</div>
<div class="controls">
  <input type="text" id="search" placeholder="Search patient…" oninput="filter()">
  <select id="qfilt" onchange="filter()">
    <option value="">All quality</option>
    <option value="Good">Good</option>
    <option value="Medium">Medium</option>
    <option value="Poor">Poor</option>
  </select>
  <select id="efcat" onchange="filter()">
    <option value="">All EF</option>
    <option value="severe">Severe (&lt;35%)</option>
    <option value="reduced">Reduced (35–49%)</option>
    <option value="normal">Normal (50–65%)</option>
    <option value="high">High (&gt;65%)</option>
    <option value="degenerate">Degenerate</option>
  </select>
  <select id="sort" onchange="sortCards()">
    <option value="pid">Sort: patient ID</option>
    <option value="ef_asc">Sort: EF low→high</option>
    <option value="ef_desc">Sort: EF high→low</option>
  </select>
  <span class="count" id="count"></span>
</div>
<div id="grid">
""" + "\n".join(items) + """
</div>
<div style="padding:16px 20px;font-size:12px;color:var(--muted);">
  <a href="../frontend/camus.html">← Beating LV demo (patient0001)</a> ·
  <a href="../frontend/ar.html">3D reconstruction AR</a>
</div>
<script>
const cards = Array.from(document.querySelectorAll('.card'));
function filter(){
  const s = document.getElementById('search').value.toLowerCase();
  const q = document.getElementById('qfilt').value;
  const e = document.getElementById('efcat').value;
  let n = 0;
  cards.forEach(c=>{
    const show = (!s || c.dataset.pid.includes(s))
      && (!q || c.dataset.quality === q)
      && (!e || c.dataset.badge === e);
    c.classList.toggle('hidden', !show);
    if(show) n++;
  });
  document.getElementById('count').textContent = n + ' / ' + cards.length + ' patients';
}
function sortCards(){
  const v = document.getElementById('sort').value;
  const grid = document.getElementById('grid');
  const sorted = [...cards].sort((a,b)=>{
    if(v==='ef_asc')  return parseFloat(a.dataset.ef) - parseFloat(b.dataset.ef);
    if(v==='ef_desc') return parseFloat(b.dataset.ef) - parseFloat(a.dataset.ef);
    return a.dataset.pid.localeCompare(b.dataset.pid);
  });
  sorted.forEach(c=>grid.appendChild(c));
  filter();
}
filter();
</script>
</body>
</html>
"""
    return html


def main():
    os.makedirs(GALLERY_DIR, exist_ok=True)

    # load existing results so we know which patients are valid
    results = {}
    if os.path.exists(RESULTS_CSV):
        for row in csv.DictReader(open(RESULTS_CSV)):
            results[row["patient"]] = row

    patients = sorted(glob.glob(os.path.join(DB, "patient*")))
    n = len(patients)
    print(f"Rendering {n} patient thumbnails -> {GALLERY_DIR}")

    cards = []
    t0 = time.time()
    ok = fail = 0

    for i, pdir in enumerate(patients, 1):
        pid = os.path.basename(pdir)
        out_png = os.path.join(GALLERY_DIR, f"{pid}.png")
        row = results.get(pid, {})
        phys = row.get("physiological") == "True"
        ef   = float(row["EF_pct"])  if row.get("EF_pct")      else 0.0
        edv  = float(row["EDV_mL"])  if row.get("EDV_mL")      else 0.0
        esv  = float(row["ESV_mL"])  if row.get("ESV_mL")      else 0.0
        ref  = row.get("reference_ef", "")
        qual = row.get("image_quality", "")

        # reconstruct the ED mesh (fast — already verified above)
        if not os.path.exists(out_png):
            try:
                r = cb.reconstruct_phase(pdir, pid, "ED")
                render_thumbnail(r["verts"], r["faces"], out_png)
                ok += 1
            except Exception as e:
                # create a placeholder dark tile so the gallery still shows the slot
                fig = plt.figure(figsize=(2,2.5), facecolor="#0b0e13")
                ax = fig.add_subplot(111); ax.axis("off")
                ax.text(0.5,0.5, "err", color="#666", ha="center", va="center",
                        transform=ax.transAxes, fontsize=10)
                fig.savefig(out_png, dpi=100, facecolor="#0b0e13")
                plt.close(fig)
                fail += 1
        else:
            ok += 1

        cards.append(dict(pid=pid, ef=ef, edv=edv, esv=esv,
                          ref_ef=ref, quality=qual, phys=phys))

        if i % 50 == 0 or i == n:
            elapsed = time.time() - t0
            eta = (n - i) / (i / elapsed) if elapsed > 0 else 0
            print(f"  [{i:3d}/{n}]  rendered={ok}  fail={fail}"
                  f"  elapsed={elapsed:.0f}s  eta={eta:.0f}s")
        elif i % 10 == 0:
            print(f"  [{i:3d}/{n}]...", end="\r", flush=True)

    # write gallery HTML
    html = build_gallery_html(cards)
    with open(GALLERY_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDone.  {ok} thumbnails  |  {fail} failed")
    print(f"Gallery -> {GALLERY_HTML}")
    print(f"Elapsed: {time.time()-t0:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
