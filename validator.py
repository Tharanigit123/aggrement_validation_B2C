"""
validator.py

Lightweight, execution-safe Agreement Validation module.
Provides:
- extract_text_and_images(pdf_path) -> (text, pages)
- AgreementValidator(config_path='config.yaml').validate(main_pdf, client_pdf, documents=..., document_names=...) -> dict
- simple_diff, fuzzy_ratio, clause_similarity helpers

Optional libraries (pdfplumber, pdf2image, pytesseract) are used if installed.
"""

from __future__ import annotations
import re
import yaml
from difflib import SequenceMatcher
from typing import List, Tuple, Any, Dict

__all__ = ["extract_text_and_images", "AgreementValidator", "simple_diff", "fuzzy_ratio", "clause_similarity"]

# -------------------------
# Helpers
# -------------------------
def simple_diff(a: str, b: str) -> Dict[str, List[str]]:
    s = SequenceMatcher(None, a or "", b or "")
    adds: List[str] = []
    removes: List[str] = []
    for tag, i1, i2, j1, j2 in s.get_opcodes():
        if tag == "insert":
            adds.append((b or "")[j1:j2])
        elif tag == "delete":
            removes.append((a or "")[i1:i2])
    return {"added": adds, "removed": removes}

def fuzzy_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    a_tokens = set(a.lower().split())
    b_tokens = set(b.lower().split())
    if not a_tokens or not b_tokens:
        return 0.0
    inter = a_tokens.intersection(b_tokens)
    union = a_tokens.union(b_tokens)
    token_score = len(inter) / len(union)
    seq = SequenceMatcher(None, a, b).ratio()
    return float(0.6 * token_score + 0.4 * seq)

def clause_similarity(a: str, b: str) -> float:
    return fuzzy_ratio(a, b)

# -------------------------
# Minimal PDF extractor
# -------------------------
def extract_text_and_images(pdf_path: str) -> Tuple[str, List[Any]]:
    """
    Try pdfplumber + pdf2image. If not available, return empty text and empty pages list.
    """
    try:
        import pdfplumber  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except Exception:
        return "", []

    texts: List[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                texts.append(page.extract_text() or "")
    except Exception:
        texts = [""]

    try:
        pil_pages = convert_from_path(pdf_path, dpi=200)
    except Exception:
        pil_pages = []

    return "\n\n".join(texts), pil_pages

# -------------------------
# AgreementValidator
# -------------------------
class AgreementValidator:
    DEFAULT_CONFIG = {
        "pan_regex": r"\b([A-Z]{5}[0-9]{4}[A-Z])\b",
        "gst_regex": r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b",
        "coi_keywords": ["certificate of incorporation", "incorporation certificate"],
        "ratecard_keywords": ["rate card", "rate-card", "price list"],
        "similarity_threshold": 0.75,
    }

    def __init__(self, config_path: str = "config.yaml") -> None:
        cfg = {}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            cfg = {}

        merged = dict(AgreementValidator.DEFAULT_CONFIG)
        merged.update(cfg)
        self.cfg = merged

        pan_pattern = self.cfg.get("pan_regex") or r""
        gst_pattern = self.cfg.get("gst_regex") or r""
        try:
            self.pan_re = re.compile(pan_pattern)
        except re.error:
            self.pan_re = re.compile(AgreementValidator.DEFAULT_CONFIG["pan_regex"])
        try:
            self.gst_re = re.compile(gst_pattern)
        except re.error:
            self.gst_re = re.compile(AgreementValidator.DEFAULT_CONFIG["gst_regex"])

        self.coi_keywords = [k.lower() for k in self.cfg.get("coi_keywords", [])]
        self.ratecard_keywords = [k.lower() for k in self.cfg.get("ratecard_keywords", [])]
        self.sim_threshold = float(self.cfg.get("similarity_threshold", 0.75))

    def _search_pan_gst(self, text: str) -> Tuple[List[str], List[str]]:
        if not text:
            return [], []
        pan = self.pan_re.findall(text)
        gst = self.gst_re.findall(text)
        return pan, gst

    def _keyword_check(self, text: str, keywords: List[str]) -> List[str]:
        t = (text or "").lower()
        return [k for k in keywords if k in t]

    def validate(self, main_pdf: str, client_pdf: str, documents: List[str] = None, document_names: List[str] = None) -> Dict[str, Any]:
        main_text, main_pages = extract_text_and_images(main_pdf)
        client_text, client_pages = extract_text_and_images(client_pdf)

        if not (main_text and main_text.strip()):
            main_text = ""
        if not (client_text and client_text.strip()):
            client_text = ""

        pan_main, gst_main = self._search_pan_gst(main_text)
        pan_client, gst_client = self._search_pan_gst(client_text)

        coi_main = self._keyword_check(main_text, self.coi_keywords)
        coi_client = self._keyword_check(client_text, self.coi_keywords)

        rate_main = self._keyword_check(main_text, self.ratecard_keywords)
        rate_client = self._keyword_check(client_text, self.ratecard_keywords)

        diff = simple_diff(main_text, client_text)

        main_lines = [l.strip() for l in (main_text or "").splitlines() if l.strip()][:200]
        client_lines = [l.strip() for l in (client_text or "").splitlines() if l.strip()][:200]

        similarities = []
        for m in main_lines[:20]:
            best = 0.0
            best_line = None
            for c in client_lines[:40]:
                sim = clause_similarity(m, c)
                if sim > best:
                    best = sim
                    best_line = c
            similarities.append({"main": m, "best_match": best_line, "score": best})

        documents = documents or []
        document_names = document_names or []
        documents_summary = {}
        for idx, doc_path in enumerate(documents):
            doc_name = document_names[idx] if idx < len(document_names) else f"document_{idx+1}.pdf"
            try:
                d_text, d_pages = extract_text_and_images(doc_path)
                if not (d_text and d_text.strip()):
                    d_text = ""
            except Exception:
                d_text = ""
            pan_d, gst_d = self._search_pan_gst(d_text)
            coi_d = self._keyword_check(d_text, self.coi_keywords)
            rate_d = self._keyword_check(d_text, self.ratecard_keywords)
            documents_summary[doc_name] = {
                "pan": pan_d,
                "gst": gst_d,
                "coi_keywords": coi_d,
                "rate_keywords": rate_d,
                "text_snippet": (d_text or "")[:1000]
            }

        summary = {
            "pan": {"main": pan_main, "client": pan_client},
            "gst": {"main": gst_main, "client": gst_client},
            "coi_keywords": {"main": coi_main, "client": coi_client},
            "rate_keywords": {"main": rate_main, "client": rate_client},
            "diff": diff,
            "clause_similarity_samples": similarities,
            "documents": documents_summary,
        }
        return summary

if __name__ == "__main__":
    print("Agreement Validator module loaded. Use tests or import it.")
