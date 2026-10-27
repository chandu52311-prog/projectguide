import fitz  # PyMuPDF
import re
import math

class SimulationMathEngine:
    """
    IEEE Standards compliant sizing engine for Power Electronics & Grid-Tied Systems.
    Calculates missing passive components from nominal parameters.
    """
    def __init__(self, v_dc=400.0, v_grid=230.0, f_grid=50.0, p_rated=5000.0, f_sw=10000.0):
        self.v_dc = float(v_dc)
        self.v_grid = float(v_grid)
        self.f_grid = float(f_grid)
        self.p_rated = float(p_rated)
        self.f_sw = float(f_sw)
        self.omega_g = 2 * math.pi * self.f_grid

    def calculate_lcl_filter(self, ripple_ratio=0.15, att_ratio=0.20):
        """
        Derives Inverter-side Inductor (L1), Grid-side Inductor (L2),
        Filter Capacitor (Cf), and Damping Resistor (Rd) via IEEE Std 519.
        """
        # Nominal Phase Current
        i_max = (math.sqrt(2) * self.p_rated) / (3 * self.v_grid)
        delta_i_lmax = ripple_ratio * i_max

        # 1. Inverter-side Inductor (L1) based on max current ripple
        l1 = self.v_dc / (6 * self.f_sw * delta_i_lmax)

        # 2. Base Capacitance (Cb) & Max Filter Capacitance (Cf <= 5% of Cb for power factor guard)
        z_base = (3 * (self.v_grid ** 2)) / self.p_rated
        c_base = 1 / (self.omega_g * z_base)
        c_f = 0.05 * c_base

        # 3. Grid-side Inductor (L2) with desired harmonic attenuation
        # Harmonic attenuation factor k_a = 1 / |1 + r*(1 - L1*Cf*omega_sw^2)| where r = L2/L1
        omega_sw = 2 * math.pi * self.f_sw
        r_factor = 1.0 / (att_ratio * (l1 * c_f * (omega_sw ** 2) - 1))
        l2 = max(0.2 * l1, r_factor * l1)

        # 4. Resonance Frequency Check (Must be between 10*fg and 0.5*fsw)
        f_res = (1 / (2 * math.pi)) * math.sqrt((l1 + l2) / (l1 * l2 * c_f))
        
        # 5. Damping Resistor (Rd = 1 / (3 * omega_res * Cf))
        omega_res = 2 * math.pi * f_res
        r_d = 1 / (3 * omega_res * c_f)

        return {
            "I_phase_peak": round(i_max, 2),
            "L1_inverter_H": round(l1, 6),
            "L2_grid_H": round(l2, 6),
            "C_filter_F": round(c_f, 8),
            "f_resonance_Hz": round(f_res, 1),
            "R_damping_Ohm": round(r_d, 3),
            "status": "CONVERGED" if (10 * self.f_grid < f_res < 0.5 * self.f_sw) else "RESONANCE_WARNING"
        }

    def generate_matlab_script(self, lcl_results, novelty_type="FOC_COMPARISON"):
        """
        Compiles a fully runnable .m file with ODE solver settings and block mask variables.
        """
        m_code = f"""%% =========================================================================
%% AUTONOMOUS RESEARCH SIMULATION WORKBENCH - RUNNABLE HARNESS
%% Generated according to IEEE Standard Specifications
%% =========================================================================
clear; clc; close all;

%% --- System Base Ratings ---
V_dc = {self.v_dc};                  % DC Bus Potential (V)
V_grid_rms = {self.v_grid};            % Grid Phase Voltage (V RMS)
f_grid = {self.f_grid};                % Nominal Grid Frequency (Hz)
P_rated = {self.p_rated};              % Active Power Output (W)
f_sw = {self.f_sw};                 % Inverter Switching Frequency (Hz)
T_s = 1/(10*f_sw);               % Continuous Solver Max Step Size (s)

%% --- Auto-Sized LCL Filter Matrices (IEEE Std 519) ---
L1 = {lcl_results['L1_inverter_H']};             % Inverter-side Inductor (H)
L2 = {lcl_results['L2_grid_H']};             % Grid-side Inductor (H)
Cf = {lcl_results['C_filter_F']};          % Shunt Capacitance (F)
Rd = {lcl_results['R_damping_Ohm']};             % Passive Damping Resistance (Ohm)
f_res = {lcl_results['f_resonance_Hz']};          % Calculated Resonance Frequency (Hz)

%% --- Current Controller Parameters (PI Tuning via Modulus Optimum) ---
tau_filter = L1 / ({self.v_dc} / (2*sqrt(3)));
Ti = L1 / 0.1;                   % Integral Time Constant
Kp_i = L1 / (2 * (1/f_sw));      % Proportional Gain (Current Loop)
Ki_i = Kp_i / Ti;                % Integral Gain (Current Loop)

%% --- Novelty Comparative Branch: {novelty_type} ---
switch '{novelty_type}'
    case 'FOC_COMPARISON'
        disp('[INFO] Configuring Field-Oriented Control (d-q rotating frame) state arrays.');
        omega_sync = 2 * pi * f_grid;
        decoupling_factor = omega_sync * L1;
    case 'LLCL_EXTENSION'
        disp('[INFO] Injecting series LC trap branch for f_sw notch attenuation.');
        Cf_trap = Cf * 0.9;
        Lf_trap = 1 / ((2*pi*f_sw)^2 * Cf_trap);
    otherwise
        disp('[INFO] Running Baseline Sizing Array.');
end

disp('>>> Parameters loaded successfully. Launch Simulink harness (.slx) to execute.');
"""
        return m_code


class PDFParameterExtractor:
    """
    Extracts numerical electrical matrix ratings directly from IEEE text streams.
    """
    @staticmethod
    def extract_ratings(pdf_bytes):
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""
        for page in doc:
            full_text += page.get_text() + " "

        extracted = {}

        # 1. DC Voltage extraction (e.g., Vdc = 400V, 400 V, DC-link 700 V)
        vdc_match = re.search(r'(?:Vdc|V_dc|DC[- ]link voltage|DC bus)\s*[:=~]?\s*(\d{2,4})\s*V', full_text, re.IGNORECASE)
        extracted['v_dc'] = float(vdc_match.group(1)) if vdc_match else 400.0

        # 2. Grid Voltage (e.g., 230 V, 415 V, 110 V)
        vgrid_match = re.search(r'(?:Grid voltage|AC voltage|V_grid|Vs)\s*[:=~]?\s*(\d{2,3})\s*V', full_text, re.IGNORECASE)
        extracted['v_grid'] = float(vgrid_match.group(1)) if vgrid_match else 230.0

        # 3. Switching Frequency (e.g., 10 kHz, 20 kHz, 5000 Hz)
        fsw_match = re.search(r'(?:switching frequency|f_sw|fsw|fs)\s*[:=~]?\s*(\d{1,3}(?:\.\d+)?)\s*(k?Hz)', full_text, re.IGNORECASE)
        if fsw_match:
            val = float(fsw_match.group(1))
            unit = fsw_match.group(2).lower()
            extracted['f_sw'] = val * 1000.0 if 'k' in unit else val
        else:
            extracted['f_sw'] = 10000.0

        # 4. Rated Power (e.g., 5 kW, 10 kW, 5000 W)
        prated_match = re.search(r'(?:rated power|nominal power|P_rated|Pout)\s*[:=~]?\s*(\d{1,4}(?:\.\d+)?)\s*(k?W)', full_text, re.IGNORECASE)
        if prated_match:
            val = float(prated_match.group(1))
            unit = prated_match.group(2).lower()
            extracted['p_rated'] = val * 1000.0 if 'k' in unit else val
        else:
            extracted['p_rated'] = 5000.0

        return extracted
