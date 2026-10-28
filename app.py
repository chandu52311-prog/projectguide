import io
import logging
import os
import re
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from bundle_generator import MODEL_NAMES, compile_deliverable_bundle
from pdf_engine import PDFParameterExtractor
from sizing_math import SimulationMathEngine

log = logging.getLogger("projectguide")
MAX_UPLOAD = 25 * 1024 * 1024
BRANCHES = {"EEE", "ECE", "CSE", "MECH"}
LEVELS = {"B.Tech", "M.Tech"}
# Payment: set PG_REQUIRE_PAYMENT=1 once a real gateway verification is wired into verify_payment().
REQUIRE_PAYMENT = os.getenv("PG_REQUIRE_PAYMENT", "0") == "1"

app = FastAPI(title="ProjectGuide API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _read(upload: UploadFile) -> bytes:
    data = upload.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File too large (limit 25 MB).")
    if not data:
        raise HTTPException(400, f"{upload.filename} is empty.")
    return data


def verify_payment(utr: str) -> None:
    """A UTR typed by the user proves nothing. Verify via your payment provider's API/webhook here."""
    if not REQUIRE_PAYMENT:
        log.warning("Payment verification is DISABLED (dev mode).")
        return
    if not re.fullmatch(r"\d{12}", utr or ""):
        raise HTTPException(402, "Invalid UTR format.")
    raise HTTPException(501, "Payment gateway verification is not implemented yet.")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/audit-paper")
def audit_paper(paper: UploadFile = File(...), abstract: Optional[UploadFile] = File(None), notes: str = Form("")):
    pdf = _read(paper)
    ratings, provenance = PDFParameterExtractor.extract_ratings(pdf, paper.filename or "paper.pdf")

    abs_bytes = _read(abstract) if abstract is not None else None
    novelty, source, keywords = PDFParameterExtractor.extract_novelty_type(
        abs_bytes, abstract.filename if abstract else "", notes)

    try:
        engine = SimulationMathEngine(ratings["v_dc"], ratings["v_grid"], ratings["f_grid"],
                                      ratings["p_rated"], ratings["f_sw"])
        lcl = engine.calculate_lcl_filter(llcl=(novelty == "LLCL_EXTENSION"))
    except ValueError as e:
        raise HTTPException(422, str(e))

    return {
        "ratings": ratings,
        "provenance": provenance,
        "novelty_type": novelty,
        "novelty_source": source,
        "novelty_keywords": keywords,
        "required_models": MODEL_NAMES,
        "lcl_sizing": lcl,
    }


@app.post("/api/generate-kit")
def generate_kit(
    branch: str = Form("EEE"), level: str = Form("M.Tech"),
    v_dc: float = Form(400.0), v_grid: float = Form(230.0), f_grid: float = Form(50.0),
    p_rated: float = Form(5000.0), f_sw: float = Form(10000.0),
    novelty_type: str = Form("LLCL_EXTENSION"), custom_notes: str = Form(""),
    provenance: str = Form("{}"), utr: str = Form(""),
):
    if branch not in BRANCHES or level not in LEVELS:
        raise HTTPException(400, "Invalid branch or level.")
    if branch != "EEE":
        raise HTTPException(501, "Only the EEE (power-electronics / Simulink) kit is implemented.")
    if novelty_type not in {"LLCL_EXTENSION", "GMPPT_SOLAR", "BATTERY_STORAGE", "BASELINE"}:
        raise HTTPException(400, "Invalid novelty type.")
    verify_payment(utr)

    try:
        import json
        prov = json.loads(provenance) if provenance else {}
        engine = SimulationMathEngine(v_dc, v_grid, f_grid, p_rated, f_sw)
        lcl = engine.calculate_lcl_filter(llcl=(novelty_type == "LLCL_EXTENSION"))
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e))

    init_m = engine.generate_matlab_script(lcl, novelty_type)
    ratings = {"v_dc": v_dc, "v_grid": v_grid, "f_grid": f_grid, "p_rated": p_rated, "f_sw": f_sw}
    zip_buf = compile_deliverable_bundle(branch, level, ratings, lcl, init_m, novelty_type, custom_notes, prov)
    data = zip_buf.getvalue()
    fname = f"ProjectGuide_{branch}_{level.replace('.', '')}_Kit.zip"
    return StreamingResponse(io.BytesIO(data), media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"',
                                      "Content-Length": str(len(data)),
                                      "Access-Control-Expose-Headers": "Content-Disposition"})
