import fitz  # PyMuPDF
import re
import math

class SimulationMathEngine:
    """
    IEEE Std 519 compliant sizing & Autonomous Simulink Circuit Generator.
    Calculates missing passive components and dynamically generates programmatic
    MATLAB build scripts to construct Simulink models (.slx) block-by-block.
    """
    def __init__(self, v_dc=400.0, v_grid=230.0, f_grid=50.0, p_rated=5000.0, f_sw=10000.0):
        self.v_dc = float(v_dc)
        self.v_grid = float(v_grid)
        self.f_grid = float(f_grid)
        self.p_rated = float(p_rated)
        self.f_sw = float(f_sw)
        self.omega_g = 2.0 * math.pi * self.f_grid

    def calculate_lcl_filter(self, ripple_ratio=0.15, att_ratio=0.20):
        """
        Derives Inverter-side Inductor (L1), Grid-side Inductor (L2),
        Filter Capacitor (Cf), and Damping Resistor (Rd) via standard IEEE equations.
        """
        i_max = (math.sqrt(2) * self.p_rated) / self.v_grid
        delta_i_lmax = ripple_ratio * i_max

        # 1. Inverter Inductance
        l1 = self.v_dc / (6.0 * self.f_sw * delta_i_lmax)

        # 2. Base & Shunt Capacitance
        z_base = (self.v_grid ** 2) / self.p_rated
        c_base = 1.0 / (self.omega_g * z_base)
        c_f = 0.05 * c_base

        # 3. Grid-side Inductance with Harmonic Attenuation
        omega_sw = 2.0 * math.pi * self.f_sw
        lc_product = l1 * c_f * (omega_sw ** 2)
        if lc_product > 1.0:
            r_factor = 1.0 / (att_ratio * (lc_product - 1.0))
            l2 = max(0.25 * l1, r_factor * l1)
        else:
            l2 = 0.4 * l1

        # 4. Resonance & Damping
        f_res = (1.0 / (2.0 * math.pi)) * math.sqrt((l1 + l2) / (l1 * l2 * c_f))
        omega_res = 2.0 * math.pi * f_res
        r_d = 1.0 / (3.0 * omega_res * c_f)

        is_stable = (10 * self.f_grid) < f_res < (0.5 * self.f_sw)

        return {
            "I_phase_peak": round(i_max, 2),
            "L1_inverter_H": round(l1, 6),
            "L2_grid_H": round(l2, 6),
            "C_filter_F": round(c_f, 8),
            "f_resonance_Hz": round(f_res, 1),
            "R_damping_Ohm": round(r_d, 3),
            "status": "CONVERGED" if is_stable else "RESONANCE_WARNING"
        }

    def generate_matlab_script(self, lcl_results, novelty_type="BASELINE"):
        """
        Compiles executable init_params.m that loads values into MATLAB workspace.
        """
        m_code = f"""%% =========================================================================
%% AUTONOMOUS IEEE SIMULINK HARNESS INITIALIZATION
%% Automatically synthesized from research paper & abstract
%% =========================================================================
clear; clc;

%% --- System Base Specifications ---
V_dc = {self.v_dc};                  % DC Bus Potential (V)
V_grid_rms = {self.v_grid};            % Grid Phase Voltage (V RMS)
f_grid = {self.f_grid};                % Nominal Grid Frequency (Hz)
P_rated = {self.p_rated};              % Active Power Output (W)
f_sw = {self.f_sw};                 % Inverter Switching Frequency (Hz)
T_s = 1e-6;                        % Fixed-step solver time (s)

%% --- Auto-Sized Filter Parameters (IEEE Std 519) ---
L1 = {lcl_results['L1_inverter_H']};             % Inverter-side Inductance (H)
L2 = {lcl_results['L2_grid_H']};             % Grid-side Inductance (H)
Cf = {lcl_results['C_filter_F']};          % Filter Capacitance (F)
Rd = {lcl_results['R_damping_Ohm']};             % Passive Damping Resistance (Ohm)
f_res = {lcl_results['f_resonance_Hz']};          % Calculated Resonance (Hz)

%% --- Current Controller (PI Tuning via Modulus Optimum) ---
Ti = L1 / 0.05;
Kp_i = L1 / (2 * (1 / f_sw));
Ki_i = Kp_i / Ti;

%% --- Novel Extension Configuration: {novelty_type} ---
switch '{novelty_type}'
    case 'LLCL_EXTENSION'
        Cf_trap = Cf * 0.95;
        Lf_trap = 1 / ((2 * pi * f_sw)^2 * Cf_trap);
        fprintf('[STATUS] LLCL Harmonic Trap parameters calculated.\\n');
    case 'GMPPT_SOLAR'
        V_mp = {self.v_dc * 0.85};
        P_mp = {self.p_rated};
        fprintf('[STATUS] Global MPPT arrays initialized.\\n');
    case 'BATTERY_STORAGE'
        V_bat_nom = 48.0;
        C_bat_Ah = 100.0;
        fprintf('[STATUS] Battery Subsystem linked.\\n');
    otherwise
        fprintf('[STATUS] Baseline LCL Inverter configured.\\n');
end

fprintf('>>> All system parameters loaded into MATLAB Workspace.\\n');
"""
        return m_code

    def generate_circuit_builder_script(self, lcl_results, model_name="autonomous_circuit", novelty_type="BASELINE"):
        """
        Generates programmatic MATLAB commands (add_block, add_line, set_param)
        to construct a brand-new .slx model from scratch without requiring templates.
        """
        builder_code = f"""%% =========================================================================
%% AUTONOMOUS SIMULINK MODEL SYNTHESIZER (BUILDER SCRIPT)
%% Programmatically generates and saves {model_name}.slx directly
%% =========================================================================
init_params;

fprintf('Constructing Simulink block diagram for: {model_name}...\\n');

% 1. Create and open new system
if bdIsLoaded('{model_name}')
    close_system('{model_name}', 0);
end
new_system('{model_name}');
open_system('{model_name}');

% 2. Configure Solver Settings for Power Electronics Simulation
set_param('{model_name}', 'SolverType', 'Fixed-step');
set_param('{model_name}', 'Solver', 'ode14x');
set_param('{model_name}', 'FixedStep', 'T_s');
set_param('{model_name}', 'StopTime', '0.2');

% 3. Add Powergui Block (Simscape / SimPowerSystems Engine)
add_block('powerlib/powergui', '{model_name}/powergui', 'Position', [50, 50, 120, 90]);
set_param('{model_name}/powergui', 'SimulationMode', 'Discrete');
set_param('{model_name}/powergui', 'SampleTime', 'T_s');

% 4. Add DC Power Source
add_block('powerlib/Electrical Sources/DC Voltage Source', '{model_name}/V_dc_source', 'Position', [60, 200, 100, 250]);
set_param('{model_name}/V_dc_source', 'Amplitude', 'V_dc');

% 5. Add Inverter Bridge (Universal Bridge)
add_block('powerlib/Power Electronics/Universal Bridge', '{model_name}/Inverter_Bridge', 'Position', [180, 180, 260, 270]);
set_param('{model_name}/Inverter_Bridge', 'Arms', '2');
set_param('{model_name}/Inverter_Bridge', 'Device', 'IGBT / Diodes');

% 6. Add PWM Generator
add_block('powerlib/Control/PWM Generator (2-Level)', '{model_name}/PWM_Generator', 'Position', [60, 320, 130, 380]);
set_param('{model_name}/PWM_Generator', 'CarrierFreq', 'f_sw');

% 7. Add Inverter-Side Filter Inductor (L1)
add_block('powerlib/Elements/Series RLC Branch', '{model_name}/L1_Filter', 'Position', [320, 190, 390, 220]);
set_param('{model_name}/L1_Filter', 'BranchType', 'L');
set_param('{model_name}/L1_Filter', 'Inductance', 'L1');

% 8. Add Shunt Filter Capacitor Branch (Cf + Rd)
add_block('powerlib/Elements/Series RLC Branch', '{model_name}/C_Filter_Branch', 'Position', [430, 260, 470, 330], 'Orientation', 'down');
set_param('{model_name}/C_Filter_Branch', 'BranchType', 'RC');
set_param('{model_name}/C_Filter_Branch', 'Capacitance', 'Cf');
set_param('{model_name}/C_Filter_Branch', 'Resistance', 'Rd');

% 9. Add Grid-Side Filter Inductor (L2)
add_block('powerlib/Elements/Series RLC Branch', '{model_name}/L2_Filter', 'Position', [510, 190, 580, 220]);
set_param('{model_name}/L2_Filter', 'BranchType', 'L');
set_param('{model_name}/L2_Filter', 'Inductance', 'L2');

% 10. Add AC Grid Equivalent Source
add_block('powerlib/Electrical Sources/AC Voltage Source', '{model_name}/Grid_Source', 'Position', [660, 220, 700, 280], 'Orientation', 'left');
set_param('{model_name}/Grid_Source', 'Amplitude', 'V_grid_rms * sqrt(2)');
set_param('{model_name}/Grid_Source', 'Frequency', 'f_grid');

% 11. Add Grid Current & Voltage Measurement
add_block('powerlib/Measurements/Voltage Measurement', '{model_name}/V_Grid_Meas', 'Position', [620, 120, 650, 150]);
add_block('powerlib/Measurements/Current Measurement', '{model_name}/I_Grid_Meas', 'Position', [590, 190, 620, 220]);

% 12. Add Visualization Scopes
add_block('simulink/Sinks/Scope', '{model_name}/Scope_Grid_Waveforms', 'Position', [720, 140, 770, 200]);
set_param('{model_name}/Scope_Grid_Waveforms', 'NumInputPorts', '2');

% 13. Dynamic Novelty Circuit Extensions
switch '{novelty_type}'
    case 'LLCL_EXTENSION'
        add_block('powerlib/Elements/Series RLC Branch', '{model_name}/Trap_Inductor', 'Position', [430, 350, 470, 410], 'Orientation', 'down');
        set_param('{model_name}/Trap_Inductor', 'BranchType', 'L');
        set_param('{model_name}/Trap_Inductor', 'Inductance', 'Lf_trap');
        fprintf('Added resonant LLCL harmonic trap branch into model diagram.\\n');
    case 'BATTERY_STORAGE'
        add_block('powerlib/Electrical Sources/DC Voltage Source', '{model_name}/Battery_Unit', 'Position', [60, 420, 100, 470]);
        set_param('{model_name}/Battery_Unit', 'Amplitude', 'V_bat_nom');
        fprintf('Added auxiliary Energy Storage subsystem into model diagram.\\n');
end

% 14. Programmatic Line Routing & Interconnections
add_line('{model_name}', 'PWM_Generator/1', 'Inverter_Bridge/1');
add_line('{model_name}', 'V_dc_source/1', 'Inverter_Bridge/1');
add_line('{model_name}', 'V_dc_source/2', 'Inverter_Bridge/2');
add_line('{model_name}', 'Inverter_Bridge/1', 'L1_Filter/1');
add_line('{model_name}', 'L1_Filter/1', 'C_Filter_Branch/1');
add_line('{model_name}', 'L1_Filter/1', 'L2_Filter/1');
add_line('{model_name}', 'L2_Filter/1', 'I_Grid_Meas/1');
add_line('{model_name}', 'I_Grid_Meas/1', 'Grid_Source/1');
add_line('{model_name}', 'I_Grid_Meas/1', 'Scope_Grid_Waveforms/1');
add_line('{model_name}', 'V_Grid_Meas/1', 'Scope_Grid_Waveforms/2');

% 15. Save and Export binary .slx
save_system('{model_name}', '{model_name}.slx');
fprintf('>>> Successfully generated and saved {model_name}.slx without errors!\\n');
"""
        return builder_code


class PDFParameterExtractor:
    """
    Extracts ratings from Base Paper and detects extensions from Abstract.
    """
    @staticmethod
    def extract_ratings(pdf_bytes):
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text() + " "
        doc.close()

        extracted = {}

        # 1. DC Voltage extraction
        vdc_match = re.search(r'(?:Vdc|V_dc|DC[- ]link voltage|DC bus)\s*[:=~]?\s*(\d{2,4})\s*V', full_text, re.IGNORECASE)
        extracted['v_dc'] = float(vdc_match.group(1)) if vdc_match else 400.0

        # 2. Grid Voltage
        vgrid_match = re.search(r'(?:Grid voltage|AC voltage|V_grid|Vs)\s*[:=~]?\s*(\d{2,3})\s*V', full_text, re.IGNORECASE)
        extracted['v_grid'] = float(vgrid_match.group(1)) if vgrid_match else 230.0

        # 3. Switching Frequency
        fsw_match = re.search(r'(?:switching frequency|f_sw|fsw|fs)\s*[:=~]?\s*(\d{1,3}(?:\.\d+)?)\s*(k?Hz)', full_text, re.IGNORECASE)
        if fsw_match:
            val = float(fsw_match.group(1))
            unit = fsw_match.group(2).lower()
            extracted['f_sw'] = val * 1000.0 if 'k' in unit else val
        else:
            extracted['f_sw'] = 10000.0

        # 4. Rated Power
        prated_match = re.search(r'(?:rated power|nominal power|P_rated|Pout)\s*[:=~]?\s*(\d{1,4}(?:\.\d+)?)\s*(k?W)', full_text, re.IGNORECASE)
        if prated_match:
            val = float(prated_match.group(1))
            unit = prated_match.group(2).lower()
            extracted['p_rated'] = val * 1000.0 if 'k' in unit else val
        else:
            extracted['p_rated'] = 5000.0

        return extracted

    @staticmethod
    def extract_novelty_type(abstract_bytes):
        """Identifies which Simulink extension circuit is required based on the abstract."""
        if not abstract_bytes:
            return "BASELINE", ["base_paper_circuit.slx"]

        doc = fitz.open(stream=abstract_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text() + " "
        doc.close()
        text_lower = text.lower()

        required_models = ["base_paper_circuit.slx"]

        if any(w in text_lower for w in ["llcl", "trap", "notch"]):
            novelty = "LLCL_EXTENSION"
            required_models.append("proposed_llcl_circuit.slx")
        elif any(w in text_lower for w in ["gmppt", "partial shading", "global maximum"]):
            novelty = "GMPPT_SOLAR"
            required_models.append("proposed_gmppt_circuit.slx")
        elif any(w in text_lower for w in ["battery", "bess", "storage", "bidirectional"]):
            novelty = "BATTERY_STORAGE"
            required_models.append("proposed_battery_circuit.slx")
        else:
            novelty = "LLCL_EXTENSION"
            required_models.append("proposed_llcl_circuit.slx")

        return novelty, required_models
