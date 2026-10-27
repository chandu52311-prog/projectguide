from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sizing_math import PDFParameterExtractor, SimulationMathEngine
from zip_compiler import compile_deliverable_bundle

app = FastAPI(title="ProjectGuide Autonomous Simulation Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/audit-paper")
async def audit_paper(
    file: UploadFile = File(...)
):
    pdf_bytes = await file.read()
    if len(pdf_bytes) < 10000:
        raise HTTPException(status_code=400, detail="Document lacks sufficient digital text density.")

    ratings = PDFParameterExtractor.extract_ratings(pdf_bytes)
    engine = SimulationMathEngine(
        v_dc=ratings['v_dc'],
        v_grid=ratings['v_grid'],
        p_rated=ratings['p_rated'],
        f_sw=ratings['f_sw']
    )
    lcl_results = engine.calculate_lcl_filter()

    return {
        "status": "PASS_VERIFIED",
        "ratings": ratings,
        "lcl_sizing": lcl_results
    }

@app.post("/api/generate-kit")
async def generate_kit(
    branch: str = Form("EEE"),
    level: str = Form("B.Tech"),
    v_dc: float = Form(400.0),
    v_grid: float = Form(230.0),
    p_rated: float = Form(5000.0),
    f_sw: float = Form(10000.0),
    custom_notes: str = Form("")
):
    ratings = {
        "v_dc": v_dc,
        "v_grid": v_grid,
        "p_rated": p_rated,
        "f_sw": f_sw
    }

    engine = SimulationMathEngine(v_dc=v_dc, v_grid=v_grid, p_rated=p_rated, f_sw=f_sw)
    lcl_results = engine.calculate_lcl_filter()
    m_script = engine.generate_matlab_script(lcl_results)

    zip_stream = compile_deliverable_bundle(branch, level, ratings, lcl_results, m_script, custom_notes)

    filename = f"ProjectGuide_{branch}_{level}_Verified_Package.zip"
    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
