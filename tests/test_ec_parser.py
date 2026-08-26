import tempfile
import os
from ec_parser import fallback_regex_extract, parse_ec_pdf


def test_fallback_regex_extract_basic():
    text = "The project must maintain a buffer of 30 m from the river and a 50 meters setback from the lake."
    res = fallback_regex_extract(text)
    assert 30 in res
    assert 50 in res


def test_parse_ec_pdf_fallback(monkeypatch):
    # Monkeypatch extract_text_from_pdf to return controlled text so parse_ec_pdf falls back to regex
    sample_text = "Condition: Maintain 100 m buffer from coastline. Also maintain 20 metres from any waterbody."
    monkeypatch.setattr('ec_parser.extract_text_from_pdf', lambda path: sample_text)
    # write a dummy pdf file path
    with tempfile.TemporaryDirectory() as td:
        pdf_path = os.path.join(td, 'dummy.pdf')
        # create an empty file to satisfy the interface
        open(pdf_path, 'wb').close()
        result = parse_ec_pdf(pdf_path)
        assert 'buffers_m' in result
        assert 100 in result['buffers_m']
        assert 20 in result['buffers_m']
