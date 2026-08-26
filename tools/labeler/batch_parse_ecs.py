"""Batch-parse EC PDFs and write `ec_parse.json` outputs for each run.

Usage:
  python tools/labeler/batch_parse_ecs.py --input-dir path/to/pdfs

For each PDF found, this script creates `outputs/<run-id>/ec_parse.json` containing
the result of `ec_parser.parse_ec_pdf`. If parsing fails for a file, the JSON will
include an `error` field with the exception message.
"""
from __future__ import annotations
import os
import sys
import argparse
import json
import uuid
import datetime

# Ensure repo root is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ec_parser import parse_ec_pdf


def process_pdf(path: str, out_root: str) -> dict:
    run_id = f"ecbatch-{os.path.splitext(os.path.basename(path))[0]}-{uuid.uuid4().hex[:8]}"
    out_dir = os.path.join(out_root, run_id)
    os.makedirs(out_dir, exist_ok=True)
    result = {
        'input_file': os.path.abspath(path),
        'run_id': run_id,
        'timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
    }

    try:
        parsed = parse_ec_pdf(path)
        result.update(parsed)
        # save ec_parse.json
        with open(os.path.join(out_dir, 'ec_parse.json'), 'w', encoding='utf-8') as f:
            json.dump(parsed, f, indent=2)
        # save raw_text if present
        raw = parsed.get('raw_text')
        if raw:
            with open(os.path.join(out_dir, 'ec_text.txt'), 'w', encoding='utf-8') as f:
                f.write(raw)
    except Exception as e:
        result['error'] = str(e)
        # write error file
        with open(os.path.join(out_dir, 'ec_parse.json'), 'w', encoding='utf-8') as f:
            json.dump({'buffers_m': [], 'llm_used': False, 'llm_error': str(e), 'extracted': {}}, f, indent=2)

    return result


def main():
    p = argparse.ArgumentParser(description='Batch parse EC PDFs and write ec_parse.json outputs')
    p.add_argument('--input-dir', required=True, help='Directory containing PDF files to parse')
    p.add_argument('--out-root', default='outputs', help='Root outputs directory')
    args = p.parse_args()

    input_dir = os.path.abspath(args.input_dir)
    out_root = os.path.abspath(args.out_root)
    os.makedirs(out_root, exist_ok=True)

    pdfs = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
    summary = []
    for pth in pdfs:
        print('Processing', pth)
        res = process_pdf(pth, out_root)
        summary.append(res)

    summary_path = os.path.join(out_root, f'ec_batch_summary_{datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")}.json')
    with open(summary_path, 'w', encoding='utf-8') as sf:
        json.dump(summary, sf, indent=2)

    print('Done. Summary written to', summary_path)


if __name__ == '__main__':
    main()
