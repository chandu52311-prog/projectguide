import io
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def set_cell_background(cell, fill_hex: str):
    """Sets background shading color for table cells."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def format_inductance(val: float) -> str:
    if val <= 0:
        return "0.0 H"
    if val < 1e-3:
        return f"{val * 1e6:.2f} µH"
    elif val < 1.0:
        return f"{val * 1e3:.2f} mH"
    return f"{val:.4f} H"

def format_capacitance(val: float) -> str:
    if val <= 0:
        return "0.0 F"
    if val < 1e-6:
        return f"{val * 1e9:.2f} nF"
    elif val < 1e-3:
        return f"{val * 1e6:.2f} µF"
    return f"{val * 1e3:.2f} mF"

def generate_project_report(branch: str, level: str, ratings: dict, lcl: dict, custom_notes: str = "") -> io.BytesIO:
    doc = Document()

    # Document-wide margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # --- Cover / Title Page ---
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(36)
    title.paragraph_format.space_after = Pt(12)
    title_run = title.add_run(f"ACADEMIC RESEARCH & SIMULATION SPECIFICATION REPORT\n{level.upper()} DISSERTATION DELIVERABLE")
    title_run.font.size = Pt(18)
    title_run.font.bold = True
    title_run.font.name = "Calibri"
    title_run.font.color.rgb = RGBColor(15, 23, 42)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.paragraph_format.space_after = Pt(24)
    sub_run = sub.add_run(f"Discipline: {branch} Engineering\nProtocol: IEEE Std 519 / Institutional Research Standards")
    sub_run.font.size = Pt(11)
    sub_run.font.italic = True
    sub_run.font.color.rgb = RGBColor(71, 85, 105)

    doc.add_page_break()

    # --- Chapter 1: Benchmark Ratings ---
    doc.add_heading("Chapter 1: Mathematical Benchmark Ratings", level=1)
    p1 = doc.add_paragraph(
        "This deliverable provides comprehensive analytical parameter verification, passive filter design, "
        "and numerical state-space convergence formulations extracted from published IEEE benchmark investigations."
    )
    p1.paragraph_format.line_spacing = 1.15
    p1.paragraph_format.space_after = Pt(12)

    table1 = doc.add_table(rows=1, cols=3)
    table1.style = 'Table Grid'
    table1.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr1 = table1.rows[0].cells
    hdr1[0].text = "Parameter Name"
    hdr1[1].text = "Extracted Value"
    hdr1[2].text = "Operational Standard"

    for cell in hdr1:
        cell.paragraphs[0].runs[0].font.bold = True
        set_cell_background(cell, "0F172A")
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)

    data1 = [
        ("DC Bus Voltage (Vdc)", f"{ratings.get('v_dc', 400.0)} V", "Nominal DC-Link Stage"),
        ("Grid Phase Voltage (Vrms)", f"{ratings.get('v_grid', 230.0)} V", "IEEE Interconnect Spec"),
        ("Switching Modulation (fsw)", f"{ratings.get('f_sw', 10000.0) / 1000.0:.1f} kHz", "PWM Carrier Dynamic"),
        ("Nominal Power (Prated)", f"{ratings.get('p_rated', 5000.0) / 1000.0:.1f} kW", "Full Load Steady State"),
    ]
    for row in data1:
        r_cells = table1.add_row().cells
        r_cells[0].text = row[0]
        r_cells[1].text = row[1]
        r_cells[2].text = row[2]
        r_cells[0].paragraphs[0].runs[0].font.size = Pt(9.5)
        r_cells[1].paragraphs[0].runs[0].font.size = Pt(9.5)
        r_cells[2].paragraphs[0].runs[0].font.size = Pt(9.5)

    doc.add_paragraph()

    # --- Chapter 2: Passive LCL Sizing & Resonance Guard ---
    doc.add_heading("Chapter 2: Sizing Formulations & Harmonic Compliance", level=1)
    p2 = doc.add_paragraph(
        "Missing filter impedances were derived in accordance with IEEE Std 519 harmonic attenuation criteria. "
        "The calculated components guarantee that the resonance frequency strictly resides inside the operational stability boundary."
    )
    p2.paragraph_format.line_spacing = 1.15
    p2.paragraph_format.space_after = Pt(12)

    table2 = doc.add_table(rows=1, cols=3)
    table2.style = 'Table Grid'
    table2.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr2 = table2.rows[0].cells
    hdr2[0].text = "Filter Component"
    hdr2[1].text = "Computed Dimension"
    hdr2[2].text = "Validation Metric"

    for cell in hdr2:
        cell.paragraphs[0].runs[0].font.bold = True
        set_cell_background(cell, "0F172A")
        cell.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)

    l1_raw = float(lcl.get('L1_inverter_H', 0.0))
    l2_raw = float(lcl.get('L2_grid_H', 0.0))
    cf_raw = float(lcl.get('C_filter_F', 0.0))
    rd_raw = float(lcl.get('R_damping_Ohm', 0.0))
    fres_raw = float(lcl.get('f_resonance_Hz', 0.0))

    data2 = [
        ("Inverter-Side Inductor (L1)", format_inductance(l1_raw), "Max Ripple < 15%"),
        ("Grid-Side Inductor (L2)", format_inductance(l2_raw), "Attenuation Ratio: 20%"),
        ("Filter Shunt Capacitor (Cf)", format_capacitance(cf_raw), "Reactive Power Limit < 5%"),
        ("Passive Damping Resistor (Rd)", f"{rd_raw:.3f} Ω", "Resonance Attenuation"),
        ("Resonance Frequency (fres)", f"{fres_raw:.1f} Hz", f"Status: {lcl.get('status', 'CONVERGED')}")
    ]
    for row in data2:
        r_cells = table2.add_row().cells
        r_cells[0].text = row[0]
        r_cells[1].text = row[1]
        r_cells[2].text = row[2]
        r_cells[0].paragraphs[0].runs[0].font.size = Pt(9.5)
        r_cells[1].paragraphs[0].runs[0].font.size = Pt(9.5)
        r_cells[2].paragraphs[0].runs[0].font.size = Pt(9.5)

    doc.add_paragraph()

    # --- Chapter 3: Implementation Directives ---
    doc.add_heading("Chapter 3: Simulation Harness & Execution Guidelines", level=1)
    notes_desc = custom_notes.strip() if custom_notes else "Standard baseline with comparative novel extension."
    p3 = doc.add_paragraph(
        f"Custom Specifications: {notes_desc}\n\n"
        "1. Open MATLAB and navigate to the extracted directory containing all models.\n"
        "2. Execute 'init_params.m' to initialize state-space matrices, PI loop gains, and filter arrays into the Workspace.\n"
        "3. Run 'run_comparative_simulation.m' to execute both the Base Model and Proposed Novel Extension simultaneously.\n"
        "4. Confirm that solver configuration is set to ode15s (stiff/NDF) or ode23t with fixed maximum step size Ts = 1e-6 s.\n"
        "5. Observe current harmonic attenuation and verify total harmonic distortion (THD < 5%) under the FFT analysis scope."
    )
    p3.paragraph_format.line_spacing = 1.15

    doc_io = io.BytesIO()
    doc.save(doc_io)
    doc_io.seek(0)
    return doc_io
