# NextGen Multilingual AI Health Assistant (Rural India MVP)

This project is a hackathon-ready MVP for **Problem Statement 6**: multilingual virtual health assistant for rural citizens.

## What this MVP includes

- Multilingual chat support (`en`, `hi`, `ta`, `te`, `bn`)
- Voice input + voice output in browser
- Retrieval-based health guidance from local verified dataset (medical + National Health Portal)
- Structured disease library with treatment guidance, medicine classes, home-care remedies, and emergency red flags
- Safety triage guardrails for critical symptoms
- Government scheme navigator (PM-JAY, JSY, PMMVY, eSanjeevani)
- Pincode-wise nearest hospital lookup (`/hospitals/nearest`) across India using OSM geospatial search
- Source-aware responses with confidence score

## Tech stack

- `FastAPI` backend
- Local lightweight token retriever (offline-friendly)
- `httpx` integration for pincode geocoding + nearest hospital search
- Plain HTML/CSS/JS frontend (no heavy client dependency)

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open: `http://127.0.0.1:8000`

## One-command LAN mode (no domain required)

Use this when you want stable access from other devices on same Wi-Fi:

```bash
./start-lan.sh
```

Default port is `8000`. Optional overrides:

- `PORT=8000 ./start-lan.sh`
- `SKIP_PIP_INSTALL=1 ./start-lan.sh`

## Always-on LAN mode (auto start + auto restart on Mac)

Install launchd service for LAN-only access:

```bash
python scripts/install_lan_launchd.py --load
```

Check status:

```bash
launchctl list | grep com.nextgen.health.lan
```

Check logs:

```bash
tail -f logs/backend.lan.launchd.err.log
```

## One-command stable public URL (Cloudflare named tunnel)

Prerequisite: complete one-time Cloudflare setup with your domain:

```bash
cloudflared tunnel login
cloudflared tunnel create nextgen-health
cloudflared tunnel route dns nextgen-health app.YOURDOMAIN.com
```

Ensure `~/.cloudflared/config.yml` maps the hostname to `http://localhost:8000`, then run:

```bash
./start-public.sh
```

Optional environment variables:

- `TUNNEL_NAME` (default `nextgen-health`)
- `PORT` (default `8000`)
- `SKIP_PIP_INSTALL=1` to skip dependency install on startup

## Always-on mode (auto start + auto restart on Mac)

If you want your URL available any time without manually starting commands, install launchd services:

```bash
python scripts/install_public_access_launchd.py --tunnel-name nextgen-health --load
```

What this installs:

- backend service (`uvicorn`) with `KeepAlive=true`
- Cloudflare tunnel service (`cloudflared`) with `KeepAlive=true`
- both set `RunAtLoad=true` (auto start at login/boot)

Check service status:

```bash
launchctl list | grep com.nextgen.health
```

Check logs:

```bash
tail -f logs/backend.launchd.err.log
tail -f logs/tunnel.launchd.err.log
```

To avoid "server not reached", keep this Mac awake and connected to internet.

## GitHub repo setup (shareable and runnable)

This repo includes `.gitignore` for logs/venv/certs/archives so pushes stay clean.

Initialize and push:

```bash
git init
git add .
git commit -m "Initial NextGen health assistant"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git
git push -u origin main
```

After cloning on another machine:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./start-lan.sh
```

## Stable public URL (non-expiring link approach)

`trycloudflare.com` quick tunnel links are temporary by design.
For a stable long-lived URL, deploy from GitHub to a cloud host.

### Option: Render (stable URL, no custom domain required)

This repo includes `Dockerfile` + `render.yaml`.

1. Open [https://dashboard.render.com](https://dashboard.render.com)
2. Create **New Web Service** from GitHub repo:
   `https://github.com/chitti3e-hash/nextgen-rural-health-assistant`
3. Render will build automatically and assign a stable URL like:
   `https://nextgen-rural-health-assistant.onrender.com`

Note: free plans may sleep when idle, but the URL does not expire.

### Current live deployment

- App URL: `https://nextgen-rural-health-assistant.onrender.com`
- Health check: `https://nextgen-rural-health-assistant.onrender.com/health`

### Add your custom domain on Render

1. Open Render service settings → **Custom Domains**.
2. Add your subdomain (example: `health.yourdomain.com`).
3. Copy the DNS target shown by Render.
4. In your DNS provider, create a `CNAME`:
   - Host/Name: `health`
   - Target/Value: `<render-provided-target>`
5. Return to Render and click **Verify**.
6. Enable HTTP→HTTPS redirect after SSL is issued.

## API endpoints

- `GET /health` – service health check
- `POST /chat` – health assistant response
- `GET /schemes?q=<query>&language=en` – scheme lookup
- `GET /diseases/search?q=diabetes&limit=1` – disease-wise treatment and medicine guidance
- `GET /hospitals/nearest?pincode=560001&limit=5` – nearest hospitals for Indian pincode

Sample `POST /chat`:

```json
{
  "query": "My mother has fever and weakness for two days. What should we do?",
  "language": "en",
  "mode": "text"
}
```

## Safety behavior

- Detects red-flag symptoms (chest pain, breathing difficulty, stroke/seizure cues)
- Returns emergency-first instructions for critical cases
- Avoids overconfident answers when retrieval confidence is low

## Data files

- `app/data/medical_knowledge.json` – base medical FAQ knowledge
- `app/data/national_health_portal.json` – NHP-aligned public health guidance snippets
- `app/data/disease_knowledge.json` – structured disease-treatment-medicines-remedies knowledge
- `app/data/schemes.json` – central health scheme summaries
- `app/data/pincode_hospitals_seed.json` – offline fallback for major pincodes
- `app/data/icd_category_templates.json` – ICD chapter/category mapping templates for bulk imports
- `app/data/icd_sample_input.csv` – sample ICD import input format

## ICD-10/ICD-11 bulk import pipeline

Use this when you have a large ICD extract and want to generate disease entries at scale.

```bash
python scripts/import_icd_dataset.py \
  --input app/data/icd_sample_input.csv \
  --output app/data/disease_knowledge.generated.json \
  --template app/data/icd_category_templates.json \
  --source-label "ICD-10 Bulk Import"
```

Merge into existing `app/data/disease_knowledge.json`:

```bash
python scripts/import_icd_dataset.py \
  --input your_icd_export.csv \
  --output app/data/disease_knowledge.json \
  --template app/data/icd_category_templates.json \
  --merge-existing
```

Supported input formats: `.csv`, `.json` (list of objects).
Default columns expected: `code`, `title`, `description`, `chapter`, `aliases`.
You can override column names with script flags.

## Monthly ICD refresh command (auto download + merge + sanity checks)

Run manual monthly refresh (auto-detect latest WHO release):

```bash
python scripts/refresh_icd_monthly.py \
  --release auto \
  --output app/data/disease_knowledge.json \
  --template app/data/icd_category_templates.json
```

What it does:

- Detects latest ICD-11 release from WHO releases page
- Downloads official simple tabulation package
- Filters non-disease-heavy chapters (e.g., Extension Codes)
- Imports ICD entries, merges with your custom `dis-*` records
- Validates required schema and minimum ICD row count
- Writes refresh state to `app/data/icd_refresh_state.json`

Install monthly scheduler on macOS (launchd):

```bash
python scripts/install_icd_refresh_launchd.py --day 1 --hour 3 --minute 30 --load
```

This installs job label `com.nextgen.icd-refresh` and runs monthly on local time.

Install weekly scheduler (example: Sunday 1:00 AM):

```bash
python scripts/install_icd_refresh_launchd.py --weekday 0 --hour 1 --minute 0 --load
```

## Medical safety note

- The app provides preliminary informational support only.
- It does not replace licensed medical diagnosis.
- Prescription medicines should only be started or changed by qualified doctors.

## Running tests

```bash
pytest -q
```

## Suggested next upgrades

- Plug in medical LLM + embeddings service (OpenAI, Mistral, or local model)
- Add full multilingual translation layer (IndicTrans2/NLLB)
- Integrate ABDM/health facility finder and geo-based referral
- Add conversation memory and patient profile context
