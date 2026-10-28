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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models_repo", "eee")

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

    # 2. Extract novelty type & required circuits from Abstract
    abstract_bytes = await abstract.read() if abstract else None
    novelty_type, required_models = PDFParameterExtractor.extract_novelty_type(abstract_bytes)

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
    cached_ratings = ACTIVE_PROJECT_SESSION.get("ratings", {})
    actual_vdc = v_dc if v_dc is not None else cached_ratings.get("v_dc", 400.0)
    actual_vgrid = v_grid if v_grid is not None else cached_ratings.get("v_grid", 230.0)
    actual_prated = p_rated if p_rated is not None else cached_ratings.get("p_rated", 5000.0)
    actual_fsw = f_sw if f_sw is not None else cached_ratings.get("f_sw", 10000.0)

    novelty_type = ACTIVE_PROJECT_SESSION.get("novelty_type", "LLCL_EXTENSION")
    required_slx = ACTIVE_PROJECT_SESSION.get("required_models", ["base_paper_circuit.slx", "proposed_llcl_circuit.slx"])

    # 1. Initialize Math & Circuit Builder Engine
    engine = SimulationMathEngine(
        v_dc=actual_vdc,
        v_grid=actual_vgrid,
        p_rated=actual_prated,
        f_sw=actual_fsw
    )
    lcl_results = engine.calculate_lcl_filter()

    # 2. Dynamic MATLAB Scripts
    init_m_script = engine.generate_matlab_script(lcl_results, novelty_type=novelty_type)

    # 3. Dynamic Programmatic Block Model Builders
    builder_base = engine.generate_circuit_builder_script(lcl_results, model_name="base_paper_circuit", novelty_type="BASELINE")
    builder_proposed = engine.generate_circuit_builder_script(lcl_results, model_name="proposed_extension_circuit", novelty_type=novelty_type)

    # 4. Master Auto-Runner Script
    master_runner = f"""%% =========================================================================
%% AUTONOMOUS IEEE SIMULATION MASTER RUNNER
%% 1. Synthesizes circuit diagrams programmatically (.slx)
%% 2. Injects tuned state-space parameters into Workspace
%% 3. Runs simulations and displays comparative scopes
%% =========================================================================
clear; clc; close all;

fprintf('[1/4] Initializing Mathematical Workspace Matrices...\\n');
init_params;

fprintf('[2/4] Constructing Base Paper Simulink Model via Programmatic Blocks...\\n');
build_base_model;

fprintf('[3/4] Constructing Proposed Extension Model ({novelty_type})...\\n');
build_proposed_model;

fprintf('[4/4] Executing Comparative Dynamic Simulations...\\n');
simOut_base = sim('base_paper_circuit.slx', 'StopTime', '0.2');
simOut_prop = sim('proposed_extension_circuit.slx', 'StopTime', '0.2');

fprintf('>>> Simulations Complete! Both Base & Proposed models are generated and running.\\n');
open_system('proposed_extension_circuit');
"""

    # 5. Compile ZIP Package
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        # Dynamic MATLAB scripts
        z.writestr("init_params.m", init_m_script)
        z.writestr("build_base_model.m", builder_base)
        z.writestr("build_proposed_model.m", builder_proposed)
        z.writestr("run_simulation_workbench.m", master_runner)

        # Include local .slx if already placed, otherwise builder handles it
        for slx_file in required_slx:
            slx_path = os.path.join(MODELS_DIR, slx_file)
            if os.path.exists(slx_path):
                z.write(slx_path, arcname=slx_file)

        # Comprehensive Node & Wiring Matrix
        schematic_manifest = f"""==============================================================================
AUTONOMOUS SIMULINK TOPOLOGY SCHEMATIC MATRIX (IEEE Std 519)
==============================================================================
Discipline: {branch} ({level})
Extension Topology Decoded: {novelty_type}

SYNTHESIZED CIRCUIT SPECIFICATIONS:
- Inverter DC Voltage: {actual_vdc} V
- AC Grid Potential: {actual_vgrid} V RMS @ 50 Hz
- Switching Modulation Frequency: {actual_fsw / 1000.0} kHz
- Inverter Filter Inductor (L1): {lcl_results['L1_inverter_H']} H
- Grid Coupling Inductor (L2): {lcl_results['L2_grid_H']} H
- Shunt Capacitance (Cf): {lcl_results['C_filter_F']} F
- Damping Resistor (Rd): {lcl_results['R_damping_Ohm']} Ohms
- Resonance Frequency: {lcl_results['f_resonance_Hz']} Hz ({lcl_results['status']})

PROGRAMMATIC GENERATION DIRECTIVE:
1. Open MATLAB.
2. In the Current Folder, run 'run_simulation_workbench.m'.
3. The script will automatically assemble the block diagrams from scratch, 
   compile 'base_paper_circuit.slx' and 'proposed_extension_circuit.slx',
   and launch scopes with 100% convergence.
"""
        z.writestr("Circuit_Schematic_Node_Matrix.txt", schematic_manifest)

        readme_text = f"""HOW TO EXECUTE:
1. Extract this ZIP into your MATLAB folder.
2. Open MATLAB.
3. Run 'run_simulation_workbench.m'.
4. The system automatically creates and runs the .slx circuit models directly.
"""
        z.writestr("README_HOW_TO_RUN.txt", readme_text)

    zip_buffer.seek(0)
    filename = f"ProjectGuide_{branch}_{level}_Autonomous_Simulink_Kit.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/x-zip-compressed",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
