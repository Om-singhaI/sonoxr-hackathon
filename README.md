# SonoXR / EchoAR

Turn a **2D/3D cardiac ultrasound** into a **beating 3D heart** you can hold in
mixed reality on a Meta Quest 3 — with **plain-language, uncertainty-aware AI
narration** of what you're looking at.

> Hackathon submission. This monorepo contains the backend reconstruction
> service, the marketing/demo web frontend, and the Quest 3 Unity AR client.

---

## Repository layout

| Path | What it is | Stack |
|------|-----------|-------|
| [`backend/`](backend/) | Ultrasound → `.glb` mesh + narration pipeline (FastAPI). Includes a static demo web frontend (`backend/frontend/`) and the Quest 3 Unity client source (`backend/unity/`). | Python · FastAPI · trimesh · Claude |
| [`frontend/`](frontend/) | Scroll-cinematic marketing landing page + patient viewer with an AI panel. | React · TypeScript · Vite · three.js |

---

## Quick start

### Backend (reconstruction + narration API)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # add your ANTHROPIC_API_KEY (optional — falls back to templated narration)
uvicorn app.main:app --reload
```

The golden demo path (`POST /demo`) runs the full pipeline on curated, pre-verified
input and always produces recognizable anatomy. See [`backend/DEMO_RUNBOOK.md`](backend/DEMO_RUNBOOK.md).

> The large CAMUS imaging **dataset is not committed** (license + size). Re-fetch it
> with `backend/scripts/download_sample_data.py`. The small frozen demo artifacts
> needed for `/demo` and the AR pages **are** included.

### Frontend (web landing + patient viewer)

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

API keys for the AI panel are read **server-side only** by the Vercel functions in
`frontend/api/` — see [`frontend/.env.example`](frontend/.env.example).

### Unity AR client (Quest 3)

Open `backend/unity/SonoXR_Quest3/` in Unity. Only the project **source** (`Assets/`,
`ProjectSettings/`, `Packages/`) is committed — Unity regenerates `Library/` on first
open. Copy your API keys into
`Assets/StreamingAssets/sonoxr_config.json` (a placeholder template is committed; the
real file is git-ignored).

---

## Security note

No live API keys are committed. All key material lives in git-ignored `.env` /
`sonoxr_config.json` files; `.env.example` templates show the expected variables.
