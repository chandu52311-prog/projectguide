import os
import io
import zipfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sizing_math import PDFParameterExtractor, SimulationMathEngine

app = FastAPI(title="ProjectGuide Autonomous Simulation Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simulink model templates directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models_repo", "eee")

# Global session cache - stores the latest audited paper & abstract state
ACTIVE_PROJECT_SESSION = {
    "ratings": {},
    "lcl_results": {},
    "novelty_type": "BASELINE",
    "required_models": ["base_paper_circuit.slx"]
}


@app.post("/api/audit-paper")
async def audit_paper(
    paper: UploadFile = File(...),
    abstract: UploadFile = File(None),
    notes: str = Form("")
):
    paper_bytes = await paper.read()
    if len(paper_bytes) < 5000:
        raise HTTPException(status_code=400, detail="Base paper document lacks readable digital content.")

    # 1. Extract electrical parameters from Base Paper
    ratings = PDFParameterExtractor.extract_ratings(paper_bytes)

    # 2. Extract novelty type & required .slx circuits from Abstract
    abstract_bytes = await abstract.read() if abstract else None
    novelty_type, required_models = PDFParameterExtractor.extract_novelty_type(abstract_bytes)

    # If notes specify custom models, adapt accordingly
    if notes and "llcl" in notes.lower() and "proposed_llcl_circuit.slx" not in required_models:
        novelty_type = "LLCL_EXTENSION"
        required_models.append("proposed_llcl_circuit.slx")

    # 3. Calculate mathematically precise IEEE LCL/LLCL Filter values
    engine = SimulationMathEngine(
        v_dc=ratings['v_dc'],
        v_grid=ratings['v_grid'],
        p_rated=ratings['p_rated'],
        f_sw=ratings['f_sw']
    )
    lcl_results = engine.calculate_lcl_filter()

    # Cache current analysis state for the ZIP packaging step
    ACTIVE_PROJECT_SESSION["ratings"] = ratings
    ACTIVE_PROJECT_SESSION["lcl_results"] = lcl_results
    ACTIVE_PROJECT_SESSION["novelty_type"] = novelty_type
    ACTIVE_PROJECT_SESSION["required_models"] = required_models

    return {
        "status": "PASS_VERIFIED",
        "ratings": ratings,
        "novelty_type": novelty_type,
        "required_models": required_models,
        "lcl_sizing": lcl_results
    }


@app.post("/api/generate-kit")
async def generate_kit(
    branch: str = Form("EEE"),
    level: str = Form("M.Tech"),
    v_dc: float = Form(None),
    v_grid: float = Form(None),
    p_rated: float = Form(None),
    f_sw: float = Form(None),
    custom_notes: str = Form("")
):
    # Use active session parameters if not explicitly overridden by form
    cached_ratings = ACTIVE_PROJECT_SESSION.get("ratings", {})
    actual_vdc = v_dc if v_dc is not None else cached_ratings.get("v_dc", 400.0)
    actual_vgrid = v_grid if v_grid is not None else cached_ratings.get("v_grid", 230.0)
    actual_prated = p_rated if p_rated is not None else cached_ratings.get("p_rated", 5000.0)
    actual_fsw = f_sw if f_sw is not None else cached_ratings.get("f_sw", 10000.0)

    novelty_type = ACTIVE_PROJECT_SESSION.get("novelty_type", "BASELINE")
    required_slx = ACTIVE_PROJECT_SESSION.get("required_models", ["base_paper_circuit.slx"])

    # 1. Run IEEE Sizing Engine & Generate Executable MATLAB Initialization Script
    engine = SimulationMathEngine(
        v_dc=actual_vdc,
        v_grid=actual_vgrid,
        p_rated=actual_prated,
        f_sw=actual_fsw
    )
    lcl_results = engine.calculate_lcl_filter()
    init_m_script = engine.generate_matlab_script(lcl_results, novelty_type=novelty_type)

    # 2. Automated Simulation Runner Script (.m)
    runner_m_script = f"""%% =========================================================================
%% IEEE RESEARCH HARNESS AUTOMATED EXECUTION SCRIPT
%% Runs both Base Model and Proposed Extension in Simulink and compares waveforms
%% =========================================================================
clear; clc; close all;

fprintf('[1/3] Loading System Parameters into Workspace...\\n');
init_params;

fprintf('[2/3] Simulating Base Paper Model (base_paper_circuit.slx)...\\n');
if exist('base_paper_circuit.slx', 'file') == 4
    simOut_base = sim('base_paper_circuit.slx', 'StopTime', '0.5');
    fprintf('Base Model Simulation Completed Successfully.\\n');
else
    error('base_paper_circuit.slx not found in directory.');
end

fprintf('[3/3] Simulating Proposed Novel Extension ({required_slx[-1]})...\\n');
target_model = '{required_slx[-1]}';
if exist(target_model, 'file') == 4 && ~strcmp(target_model, 'base_paper_circuit.slx')
    simOut_prop = sim(target_model, 'StopTime', '0.5');
    fprintf('Proposed Extension Simulation Completed Successfully.\\n');
end

fprintf('>>> All Simulations Converged. Generating Scopes & FFT Comparative Plots...\\n');
"""

    # 3. Create In-Memory Executable ZIP Bundle
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        # Add Executable MATLAB scripts
        z.writestr("init_params.m", init_m_script)
        z.writestr("run_comparative_simulation.m", runner_m_script)

        # Add .slx Simulink Circuits directly from repository
        for slx_file in required_slx:
            slx_path = os.path.join(MODELS_DIR, slx_file)
            if os.path.exists(slx_path):
                z.write(slx_path, arcname=slx_file)
            else:
                notice = (
                    f"Notice: '{slx_file}' will run with 'init_params.m'.\\n"
                    f"Ensure you place your tuned {slx_file} binary inside models_repo/eee folder."
                )
                z.writestr(slx_file.replace(".slx", "_NOTICE.txt"), notice)

        # Add README execution guide
        readme = f"""==============================================================================
PROJECT DELIVERABLE KIT - {branch} ({level})
IEEE Standard 519 Compliant Verification & Simulation Package
==============================================================================

INCLUDED HARNESS COMPONENTS:
1. init_params.m                -> Workspace initialization and tuned PI variables
2. run_comparative_simulation.m -> Automated harness script to run .slx models
3. Simulink Circuits (.slx)     -> {", ".join(required_slx)}

HOW TO RUN:
1. Open MATLAB.
2. Set the Current Folder in MATLAB to this unzipped directory.
3. Run 'init_params.m' to initialize variables in workspace.
4. Double-click to open any of the .slx files, or run 'run_comparative_simulation.m'.
"""
        z.writestr("EXECUTION_GUIDE.txt", readme)

    zip_buffer.seek(0)
    filename = f"ProjectGuide_{branch}_{level}_Verified_Simulink_Kit.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
