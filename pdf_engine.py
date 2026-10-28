"""
pdf_engine.py
Extract electrical ratings from a base paper and detect the novelty from an abstract.
Merges the old PyMuPDF and pypdf extractors. Every value reports its provenance
('extracted' or 'default') so the UI/report never claims "verified from source" for a default.
"""
import re
from io import BytesIO

_NUM = r"(\d+(?:\.\d+)?)"
_SEP = r"\s*(?:[:=~\u2248]|of|is|=)?\s*"


def extract_text(data: bytes, filename: str = "") -> str:
    name = (filename or "").lower()
    if data[:5] == b"%PDF-" or name.endswith(".pdf"):
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=data, filetype="pdf")
            try:
                return " ".join(page.get_text() for page in doc)
            finally:
                doc.close()
        except Exception:
            try:
                from pypdf import PdfReader
                reader = PdfReader(BytesIO(data))
                return " ".join((p.extract_text() or "") for p in reader.pages)
            except Exception:
                return ""
    if name.endswith(".docx"):
        try:
            from docx import Document
            d = Document(BytesIO(data))
            return " ".join(p.text for p in d.paragraphs)
        except Exception:
            return ""
    return data.decode("utf-8", errors="ignore")


def _first(pattern: str, text: str):
    return re.search(pattern, text)


def _scale(unit: str) -> float:
    u = unit[:1]
    return 1e6 if u == "M" else 1e3 if u in ("k", "K") else 1.0


class PDFParameterExtractor:
    DEFAULTS = {"v_dc": 400.0, "v_grid": 230.0, "f_sw": 10000.0, "p_rated": 5000.0, "f_grid": 50.0}
    RANGES = {"v_dc": (12, 3000), "v_grid": (50, 1000), "f_sw": (1000, 200000),
              "p_rated": (100, 50e6), "f_grid": (50, 60)}

    @classmethod
    def extract_ratings(cls, pdf_bytes: bytes, filename: str = "paper.pdf"):
        """Returns (ratings, provenance)."""
        text = extract_text(pdf_bytes, filename)
        text = text.replace("\u2212", "-").replace("\u00a0", " ")
        found = {}

        m = _first(r"(?i:V\s*_?\s*dc|DC[\s-]*(?:link|bus)(?:\s+voltage)?)" + _SEP + _NUM + r"\s*(k?V)\b", text)
        if m:
            found["v_dc"] = float(m.group(1)) * (1000.0 if m.group(2).lower() == "kv" else 1.0)

        m = _first(r"(?i:grid\s+(?:phase\s+)?voltage|V\s*_?\s*(?:grid|g)|ac\s+(?:grid\s+)?voltage|supply\s+voltage)"
                   + _SEP + _NUM + r"\s*(k?V)\b", text)
        if m:
            found["v_grid"] = float(m.group(1)) * (1000.0 if m.group(2).lower() == "kv" else 1.0)

        m = _first(r"(?i:switching\s+frequency|f\s*_?\s*sw|f\s*_?\s*s)" + _SEP + _NUM + r"\s*(k?Hz)", text)
        if m:
            found["f_sw"] = float(m.group(1)) * (1000.0 if m.group(2).lower().startswith("k") else 1.0)

        m = _first(r"(?i:rated\s+power|nominal\s+power|output\s+power|power\s+rating|P\s*_?\s*(?:rated|out|n))"
                   + _SEP + _NUM + r"\s*([kKM]?W)\b", text)
        if m:
            found["p_rated"] = float(m.group(1)) * _scale(m.group(2))

        m = _first(r"(?i:(?:grid|supply|fundamental|nominal)\s+frequency)" + _SEP + r"(50|60)\s*Hz", text)
        if m:
            found["f_grid"] = float(m.group(1))

        ratings, provenance = {}, {}
        for key, default in cls.DEFAULTS.items():
            lo, hi = cls.RANGES[key]
            val = found.get(key)
            if val is not None and lo <= val <= hi:
                ratings[key], provenance[key] = val, "extracted"
            else:
                ratings[key], provenance[key] = default, "default"
        return ratings, provenance

    @staticmethod
    def extract_novelty_type(abstract_bytes=None, filename: str = "", extra_text: str = ""):
        """Returns (novelty_type, source, matched_keywords)."""
        text = ""
        if abstract_bytes:
            text += extract_text(abstract_bytes, filename)
        if extra_text:
            text += " " + extra_text
        t = text.lower()

        rules = [
            ("LLCL_EXTENSION", r"\bllcl\b|harmonic\s+trap|resonant\s+trap|\bnotch\b"),
            ("GMPPT_SOLAR", r"\bgmppt\b|global\s+maximum|partial\s+shading|\bmppt\b"),
            ("BATTERY_STORAGE", r"\bbess\b|battery|energy\s+storage|bidirectional"),
        ]
        best, best_hits, best_kw = None, 0, []
        for name, pat in rules:
            hits = re.findall(pat, t)
            if len(hits) > best_hits:
                best, best_hits, best_kw = name, len(hits), sorted(set(hits))
        if best:
            return best, "detected", best_kw
        return "LLCL_EXTENSION", "defaulted", []
