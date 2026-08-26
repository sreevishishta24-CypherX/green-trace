# GREENTRACE Clause Labeler

Static labeling UI for the GREENTRACE pilot. Open `index.html` in a browser to annotate the provided seed clauses and download annotations.

How to use

1. Open `tools/labeler/index.html` in your browser (no server required).
2. Navigate clauses with Prev / Next.
3. Fill `numeric_distance`, `feature`, and optional notes.
4. Click `Download Annotations` to save `annotations.json`.

Notes

- The seed dataset is in `tools/labeler/data/seed_clauses.json` and contains synthetic examples to get started.
- This is intentionally minimal and offline-friendly. We can extend it to a simple Flask/Express server later for multi-user annotation and storage.

Server-backed multi-user labeling

- A simple Flask server is provided for multi-user annotation. It serves a server-backed UI at `index_server.html` and provides API endpoints to fetch/save/export annotations.
Run server (local)

```powershell
python tools/labeler/server.py
# then open http://127.0.0.1:5000/ in a browser
```

Run server (Docker)

Build the image from the `tools/labeler` folder and run:

```powershell
cd tools/labeler
docker build -t greentrace-labeler:latest .
docker run -p 5000:5000 greentrace-labeler:latest
```

The container serves the labeler at `http://127.0.0.1:5000/`.


CSV export

The server exposes `/api/export.csv` which returns the annotations as a CSV file with columns: `id, clause_text, annotated, annotator, numeric_distance, distance_unit, feature, qualitative_flag, note, timestamp`.

Admin UI

- An admin interface is available at `/admin` when the server is running. It lists all items, shows annotation status, and allows requeueing selected items or resetting all annotations. Use with caution (requeueing resets annotations).

Review workflow

- Admins can mark annotations as "reviewed" using the Admin UI (`/admin`) or via API (`/api/review`, `/api/review_bulk`). Reviewed items are tracked with `reviewer` and `review_timestamp` fields and included in CSV exports.

Docker image
------------

We provide a simple `Dockerfile` for the labeler that includes PDF parsing dependencies (Pillow/pdfplumber). Build and run:

```bash
cd tools/labeler
docker build -t greentrace-labeler:latest .
docker run -p 5000:5000 greentrace-labeler:latest
```

The container installs system libraries required by `Pillow` and `pdfplumber`. If you need stricter versioning, pin packages in `tools/labeler/requirements.txt`.

Compose (recommended)
---------------------

Use `docker-compose` to build and run the labeler with a persistent `data/` folder mounted into the container:

```bash
cd tools/labeler
docker-compose build
docker-compose up -d
# view logs:
docker-compose logs -f
```

The admin UI will be available at `http://localhost:5000/admin`.

Users and authentication
------------------------

- Create users (annotators/admins) with `tools/labeler/create_user.py`:

```powershell
# from repo root
python tools/labeler/create_user.py annotator1 s3cret annotator
python tools/labeler/create_user.py admin StrongPass admin
```

- This writes hashed credentials to `tools/labeler/data/users.json` which the server uses.
- Annotators must login in the labeler UI (top-right) to save annotations. Admins must login in the Admin UI to perform requeue/review actions.

Auto-fill

- The client UI supports prefill via simple regex heuristics (also available in the Python module `tools/labeler/extractor.py`).
