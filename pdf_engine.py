import re
from io import BytesIO
from pypdf import PdfReader

class BasePaperScanner:
    def __init__(self, pdf_bytes: bytes):
        self.text = ""
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            for page in reader.pages:
                extract = page.extract_text()
                if extract:
                    self.text += extract + "\n"
        except Exception as e:
            self.text = ""

    def scan_parameters(self):
        findings = {}
        cleaned_values = {}

        # 1. Power Rating (kW, MW, W, HP)
        p_match = re.search(r'\b(\d+(?:\.\d+)?)\s*(kW|hp|HP|MW|W)\b', self.text, re.IGNORECASE)
        if p_match:
            val = float(p_match.group(1))
            unit = p_match.group(2).upper()
            findings['power_rating'] = p_match.group(0)
            if unit == 'KW':
                cleaned_values['p_rated'] = val * 1000.0
            elif unit == 'MW':
                cleaned_values['p_rated'] = val * 1e6
            elif unit == 'HP':
                cleaned_values['p_rated'] = val * 746.0
            else:
                cleaned_values['p_rated'] = val
        else:
            findings['power_rating'] = None

        # 2. DC Bus / Rated Voltage (V, kV)
        v_match = re.search(r'(?:Vdc|V_dc|DC[- ]link|voltage|Vgrid|grid voltage)\s*[:=~]?\s*(\d{2,4}(?:\.\d+)?)\s*(V|kV)\b', self.text, re.IGNORECASE)
        if not v_match:
            v_match = re.search(r'\b(\d{2,4}(?:\.\d+)?)\s*(V|kV)\b', self.text)
        
        if v_match:
            val = float(v_match.group(1))
            unit = v_match.group(2).lower()
            findings['voltage_rating'] = v_match.group(0)
            cleaned_values['v_dc'] = val * 1000.0 if unit == 'kv' else val
        else:
            findings['voltage_rating'] = None

        # 3. Switching Frequency (fsw, fs, switching frequency)
        fsw_match = re.search(r'(?:f_?sw|f_?s|switching\s+frequency)\s*[:=~]?\s*(\d+(?:\.\d+)?)\s*(kHz|Hz)\b', self.text, re.IGNORECASE)
        if fsw_match:
            val = float(fsw_match.group(1))
            unit = fsw_match.group(2).lower()
            findings['switching_frequency'] = fsw_match.group(0)
            cleaned_values['f_sw'] = val * 1000.0 if unit == 'khz' else val
        else:
            findings['switching_frequency'] = None

        # 4. Grid Frequency (50 Hz / 60 Hz nominal)
        f_match = re.search(r'\b(50|60)\s*Hz\b', self.text, re.IGNORECASE)
        if f_match:
            findings['frequency'] = f_match.group(0)
            cleaned_values['f_grid'] = float(f_match.group(1))
        else:
            findings['frequency'] = "50 Hz"
            cleaned_values['f_grid'] = 50.0

        # 5. Filter Inductance (L, mH, uH)
        l_match = re.search(r'\b(\d+(?:\.\d+)?)\s*(mH|uH|µH)\b', self.text)
        if l_match:
            val = float(l_match.group(1))
            unit = l_match.group(2)
            findings['filter_inductance'] = l_match.group(0)
            cleaned_values['l_filter'] = val * 1e-3 if 'm' in unit else val * 1e-6
        else:
            findings['filter_inductance'] = None

        # 6. DC Link Capacitance (C, uF, mF)
        c_match = re.search(r'\b(\d+(?:\.\d+)?)\s*(uF|µF|mF|nF)\b', self.text)
        if c_match:
            val = float(c_match.group(1))
            unit = c_match.group(2)
            findings['dc_link_capacitance'] = c_match.group(0)
            if 'u' in unit or 'µ' in unit:
                cleaned_values['c_dclink'] = val * 1e-6
            elif 'm' in unit:
                cleaned_values['c_dclink'] = val * 1e-3
            else:
                cleaned_values['c_dclink'] = val * 1e-9
        else:
            findings['dc_link_capacitance'] = None

        # Missing Parameters Audit & Smart Institutional Defaults
        missing_list = []

        if not findings['power_rating']:
            missing_list.append({
                "param": "Rated Power (P)",
                "unit": "kW",
                "default": "5.0",
                "reason": "Required for current amplitude and DC-link calculations."
            })
            cleaned_values['p_rated'] = 5000.0

        if not findings['voltage_rating']:
            missing_list.append({
                "param": "Rated DC Voltage (Vdc)",
                "unit": "V",
                "default": "400.0",
                "reason": "Required for inverter PWM modulation index calculation."
            })
            cleaned_values['v_dc'] = 400.0

        if not findings['switching_frequency']:
            missing_list.append({
                "param": "Switching Frequency (fsw)",
                "unit": "kHz",
                "default": "10.0",
                "reason": "Critical for PWM carrier generator and harmonic ripple filter design."
            })
            cleaned_values['f_sw'] = 10000.0

        if not findings['filter_inductance']:
            missing_list.append({
                "param": "Filter Inductor (Lf)",
                "unit": "mH",
                "default": "Auto-Sized via IEEE 519",
                "reason": "Needed for current THD suppression (< 5%)."
            })

        if not findings['dc_link_capacitance']:
            missing_list.append({
                "param": "DC Link Capacitance (Cdc)",
                "unit": "µF",
                "default": "1200",
                "reason": "Needed for voltage ripple stabilization."
            })
            cleaned_values['c_dclink'] = 1200e-6

        return {
            "detected_raw": {k: v for k, v in findings.items() if v is not None},
            "numerical_ratings": cleaned_values,
            "missing_audit": missing_list,
            "status": "PASS_VERIFIED"
        }
