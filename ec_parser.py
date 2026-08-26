"""
EC condition parser: extract buffer/setback distances from an EC clearance PDF.

Workflow:
- extract_text_from_pdf(pdf_path) -> str (uses pdfplumber if available)
- parse_conditions_with_llm(text) -> dict (tries to call OpenAI if openai package & API key present)
- fallback_regex_extract(text) -> dict (regex-based extraction of distances)
- parse_ec_pdf(pdf_path) -> dict {"buffers_m": [30,50,...], "raw_text": "...", "llm_used": bool, "llm_response": ...}

Notes:
- The LLM call is optional. If openai isn't installed or API key missing, the parser falls back to regex extraction.
- The LLM prompt is designed to return a JSON list of numeric buffer distances in meters. Use function-calling or structured output where available.
"""
from typing import List, Dict, Any
import re
import os
import json
import argparse

# Try to import the labeler extractor. If that fails, attempt a file-based import fallback.
try:
    from tools.labeler.extractor import extract_clause_info
except Exception:
    # fallback: dynamic import from path
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('extractor', os.path.join(os.path.dirname(__file__), 'tools', 'labeler', 'extractor.py'))
        extractor_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(extractor_mod)
        extract_clause_info = extractor_mod.extract_clause_info
    except Exception:
        # last-resort stub
        def extract_clause_info(text: str) -> dict:
            return {"numeric_distance": None, "distance_unit": None, "feature": None, "qualitative_flag": None}


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts text from a PDF using pdfplumber if available, otherwise raises.

    Returns concatenated text of all pages.
    """
    try:
        import pdfplumber
    except Exception:
        raise RuntimeError("pdfplumber is required for PDF text extraction. Install with 'pip install pdfplumber'.")

    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                text = page.extract_text()
            except Exception:
                text = None
            if text:
                text_parts.append(text)
    return "\n\n".join(text_parts)


def fallback_regex_extract(text: str) -> List[float]:
    """Simple regex-based extraction of distances in meters from text.

    Finds patterns like '30 m', '30 meters', '50 metres', 'buffer of 100 m', 'within 200 m'.
    Returns sorted unique list of integers (meters).
    """
    if not text:
        return []
    # Normalize dashes and minus signs
    text = text.replace('\u2013', '-').replace('\u2014', '-')
    # Regex to find numbers followed by m/ meter(s) / metre(s)
    pattern = re.compile(r"(\d{1,4}(?:[\.,]\d+)?)\s*(?:m|metre|meter|meters|metres)\b", flags=re.IGNORECASE)
    matches = pattern.findall(text)
    results = []
    for m in matches:
        # remove commas, convert to float, then int meters
        m_clean = m.replace(',', '').replace(' ', '')
        try:
            val = float(m_clean)
            results.append(int(round(val)))
        except Exception:
            continue
    # Also capture phrases like 'buffer of 30 to 50 m' or '30-50 m'
    range_pattern = re.compile(r"(\d{1,4})\s*(?:to|\-|–)\s*(\d{1,4})\s*(?:m|metre|meter|meters|metres)\b", flags=re.IGNORECASE)
    for a, b in range_pattern.findall(text):
        try:
            a_i = int(a)
            b_i = int(b)
            # include both ends
            results.append(a_i)
            results.append(b_i)
        except Exception:
            continue

    # dedupe and sort
    unique = sorted(set(results))
    return unique


def parse_conditions_with_llm(text: str) -> Dict[str, Any]:
    """Attempt to parse conditions using an LLM (OpenAI). Returns dict with 'buffers_m' and raw llm response.

    If the openai package is not available or OPENAI_API_KEY not set, raises RuntimeError.
    The implementation uses a conservative function-calling style: it asks the model to return JSON with a list of buffer distances in meters.
    """
    try:
        import openai
    except Exception:
        raise RuntimeError("OpenAI python package not installed. Install with 'pip install openai' to enable LLM parsing.")

    # Ensure API key exists in environment
    if not (os.environ.get('OPENAI_API_KEY') or os.environ.get('OPENAI_API_KEY') or os.environ.get('OPENAI_API_KEY')):
        # check common env var; duplicate checks are fine
        raise RuntimeError("OPENAI_API_KEY environment variable not set. Set it to enable LLM parsing.")

    system_prompt = (
        "You are a precise information extraction assistant. "
        "Given the text of an Environmental Clearance (EC) condition document, extract any numeric buffer/setback distances that the document mandates from waterbodies or coastlines. "
        "Return output as JSON with a single key 'buffers_m' whose value is a list of integers (meters). "
        "If no explicit distances are found, return {'buffers_m': []}. Do not include any other keys."
    )

    user_prompt = f"Extract buffer distances in meters from the following EC condition text:\n\n{text[:4000]}"

    # Use Chat Completions (function-calling not required but simple JSON expected)
    resp = openai.ChatCompletion.create(
        model='gpt-4o-mini',
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=300,
        temperature=0.0,
    )
    # parse assistant content as JSON
    content = resp['choices'][0]['message']['content']
    # attempt to find JSON blob in content
    import json
    try:
        parsed = json.loads(content)
        buffers = parsed.get('buffers_m', [])
        # coerce to ints
        buffers = [int(x) for x in buffers]
        return {'buffers_m': buffers, 'llm_response': parsed}
    except Exception:
        # fallback: try to extract numbers from content using regex
        nums = fallback_regex_extract(content)
        return {'buffers_m': nums, 'llm_response': content}


def parse_ec_pdf(pdf_path: str) -> Dict[str, Any]:
    """Top-level parser: extracts text, tries LLM, falls back to regex. Returns dict with buffers_m and metadata."""
    text = extract_text_from_pdf(pdf_path)

    # Always produce a baseline extraction using the local extractor
    extractor_result = parse_ec_text(text)

    # Attempt LLM parsing when available, but do not fail if it isn't
    try:
        lm_result = parse_conditions_with_llm(text)
        # prefer LLM buffers if provided, but keep extractor info
        lm_buffers = lm_result.get('buffers_m', [])
        out = {
            'buffers_m': lm_buffers if lm_buffers else extractor_result.get('buffers_m', []),
            'llm_used': True,
            'llm_response': lm_result.get('llm_response', lm_result),
            'extracted': extractor_result.get('extracted', {}),
            'raw_text': text[:5000]
        }
        return out
    except Exception as e:
        # LLM unavailable / failed — return extractor output and error info
        return {
            'buffers_m': extractor_result.get('buffers_m', []),
            'llm_used': False,
            'llm_error': str(e),
            'extracted': extractor_result.get('extracted', {}),
            'raw_text': text[:5000]
        }


def parse_ec_text(text: str) -> Dict[str, Any]:
    """Parse arbitrary EC text using the extractor: returns normalized fields and buffer list in meters.

    This uses the labeler extractor (`extract_clause_info`) first and falls back to `fallback_regex_extract`.
    """
    if not text:
        return {'buffers_m': [], 'extracted': {}}

    try:
        info = extract_clause_info(text)
    except Exception:
        info = {"numeric_distance": None, "distance_unit": None, "feature": None, "qualitative_flag": None}

    buffers = []
    # normalize km -> meters
    if info.get('numeric_distance') is not None:
        try:
            val = float(info['numeric_distance'])
            unit = (info.get('distance_unit') or 'm').lower()
            if unit.startswith('km'):
                val_m = int(round(val * 1000))
            else:
                val_m = int(round(val))
            buffers.append(val_m)
        except Exception:
            pass

    # if no buffers found via extractor, fallback to existing regex extraction
    if not buffers:
        buffers = fallback_regex_extract(text)

    return {'buffers_m': buffers, 'extracted': info}


def _cli():
    p = argparse.ArgumentParser(description='EC text parser — extract buffer distances (meters)')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--pdf', help='Path to an EC PDF to parse')
    g.add_argument('--text', help='Raw EC text to parse')
    args = p.parse_args()
    if args.pdf:
        txt = extract_text_from_pdf(args.pdf)
    else:
        txt = args.text
    out = parse_ec_text(txt)
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    _cli()
