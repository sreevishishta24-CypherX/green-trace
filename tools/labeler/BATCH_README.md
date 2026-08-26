Batch EC PDF parsing
=====================

This script helps seed the annotation pipeline by parsing a directory of EC PDFs and writing `ec_parse.json` outputs for each file into the `outputs/` folder.

Usage
-----

Run from the repo root:

```powershell
python tools/labeler/batch_parse_ecs.py --input-dir path\to\pdfs --out-root outputs
```

Output
------
- For each PDF `file.pdf`, the script creates `outputs/ecbatch-file-<id>/ec_parse.json` and optionally `ec_text.txt` with the extracted text.
- A summary JSON `ec_batch_summary_*.json` is written inside the `--out-root` directory.

Notes
-----
- `parse_ec_pdf` uses `pdfplumber` for PDF text extraction; ensure `pdfplumber` is installed in your environment. If PDF parsing fails, the error will be recorded in the output JSON.
- These `ec_parse.json` files can be loaded into the labeler UI or used directly to build a training dataset.
