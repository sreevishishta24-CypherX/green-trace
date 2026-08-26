# Waterbody Buffer Detection Demo

This project detects whether a project point or polygon intersects a set of waterbody buffer zones and exposes the result through a clean dashboard and API.

## What is included
- Python backend with FastAPI
- Map-based demo UI
- Waterbody extraction from Overpass with a synthetic fallback
- Optional EC PDF parsing and NDWI hook
- Output artifacts for each run under `outputs/<run-id>/`

## Run locally

1. Create and activate a Python venv (Windows example):
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

2. Install Python dependencies:
   .\.venv\Scripts\pip install -r requirements.txt

3. Install frontend dependencies and build the dashboard:
   npm install
   npm run build

4. Start the API server:
   .\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000

5. Open the demo UI in a browser:
   http://127.0.0.1:8000/demo/

## Run the labeler

The optional labeler uses a local JSON user store. Create the store from the
included example and generate a fresh admin account before starting it:

```powershell
Copy-Item tools/labeler/data/users.example.json tools/labeler/data/users.json
python tools/labeler/update_user_hash.py admin "change-this-password" admin
python tools/labeler/server.py
```

The labeler is available at http://127.0.0.1:5000/ and its admin view at
http://127.0.0.1:5000/admin.

Set `LABELER_USERS_FILE` to use a different user-store path.

## Demo inputs

The dashboard accepts either:
- `bbox` as `minlon,minlat,maxlon,maxlat`
- `project_point` as `lon,lat`
- optional `project_geojson` upload
- optional EC PDF upload
- optional NDWI toggle

Sample values for a quick test:
- BBox: `77.55,12.85,77.57,12.87`
- Project point: `77.563,12.859`
- Buffers: `30,50,100`

## API quick test

You can call the backend directly with curl:

curl -X POST "http://127.0.0.1:8000/detect" -F "bbox=77.55,12.85,77.57,12.87" -F "project_point=77.563,12.859" -F "buffers=30,50,100" -F "enable_ndwi=0"

This returns JSON containing:
- `run_id`
- `report`
- `report_url`
- `evidence_url`
- `map_url`

## Output files

Each detection run writes to:
- `outputs/<run-id>/report.json`
- `outputs/<run-id>/report.pdf`
- `outputs/<run-id>/evidence.geojson`
- `outputs/<run-id>/map.png`
- `outputs/<run-id>/ec_parse.json` if an EC PDF was supplied

## Notes
- The public Overpass service is sometimes flaky; the pipeline automatically falls back to a synthetic test water geometry so the demo keeps working.
- Earth Engine / NDWI output remains optional and will only work when configured with valid credentials.

