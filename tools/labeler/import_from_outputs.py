"""Import parsed ECs from outputs/*/ec_parse.json into the labeler seed dataset.

Scans the `outputs/` directory for `ec_parse.json` files, extracts candidate clause texts
(lines that mention distances or water features) and writes a consolidated JSON file at
`tools/labeler/data/imported_from_outputs.json` which can be opened in the labeling UI.

Usage:
  python tools/labeler/import_from_outputs.py --outputs-dir outputs
"""
import os
import sys
import json
import re
from pathlib import Path

# ensure repo root on path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


DIST_RE = re.compile(r"\d{1,4}(?:[\.,]\d+)?\s*(?:m|metre|meter|km)\b", re.IGNORECASE)
FEATURE_RE = re.compile(r"\b(river|stream|waterbody|wetland|drain|lake|coast)\b", re.IGNORECASE)


def candidate_lines_from_text(text: str):
    lines = []
    if not text:
        return lines
    # split by newlines and periods to get candidate clauses
    raw_lines = re.split(r"[\n\r]+|(?<=\.)\s+", text)
    for ln in raw_lines:
        s = ln.strip()
        if not s:
            continue
        if DIST_RE.search(s) or FEATURE_RE.search(s):
            # keep reasonably short snippets
            lines.append(s[:800])
    return lines


def import_outputs(outputs_dir: str, out_file: str):
    outputs_dir = Path(outputs_dir)
    collected = []
    seen = set()
    for ec_file in outputs_dir.rglob('ec_parse.json'):
        try:
            with open(ec_file, 'r', encoding='utf-8') as f:
                parsed = json.load(f)
        except Exception:
            continue

        raw = parsed.get('raw_text') or parsed.get('raw_text', '')
        extracted = parsed.get('extracted', {})

        # candidate lines from raw text
        lines = candidate_lines_from_text(raw)

        if not lines and extracted:
            # synthesize a short clause_text from extracted fields
            parts = []
            if extracted.get('numeric_distance'):
                parts.append(f"{extracted.get('numeric_distance')} {extracted.get('distance_unit') or 'm'}")
            if extracted.get('feature'):
                parts.append(f"{extracted.get('feature')}")
            if extracted.get('qualitative_flag'):
                parts.append(f"{extracted.get('qualitative_flag')}")
            synth = ' '.join(parts) or ''
            if synth:
                lines = [synth]

        for ln in lines:
            key = (ln[:200])
            if key in seen:
                continue
            seen.add(key)
            entry = {
                'id': f"out-{len(collected)+1}",
                'clause_text': ln,
                'numeric_distance': None,
                'distance_unit': None,
                'feature': None,
                'qualitative_flag': None,
                'note': f"imported from {ec_file.parent.name}",
                'annotator': None,
                'timestamp': None
            }
            collected.append(entry)

    # merge with existing seed file if present
    seed_path = Path(__file__).parent / 'data' / 'seed_clauses.json'
    try:
        existing = json.loads(seed_path.read_text(encoding='utf-8')) if seed_path.exists() else []
    except Exception:
        existing = []

    out_list = existing + collected
    out_path = Path(__file__).parent / 'data' / 'imported_from_outputs.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out_list, f, indent=2, ensure_ascii=False)

    print(f'Imported {len(collected)} candidate clauses. Wrote {out_path}')


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--outputs-dir', default='outputs', help='Root outputs directory to scan')
    args = p.parse_args()
    import_outputs(args.outputs_dir, None)
