import re
from pypdf import PdfReader
from io import BytesIO

class BasePaperScanner:
    def __init__(self, pdf_bytes):
        self.reader = PdfReader(BytesIO(pdf_bytes))
        self.text = ""
        for page in self.reader.pages:
            extract = page.extract_text()
            if extract:
                self.text += extract + "\n"

    def scan_parameters(self):
        # 1. Regex checks for electrical ratings
        findings = {}

        # Power (kW, W, HP)
        p_match = re.search(r'(\d+(\.\d+)?)\s*(kW|hp|HP|MW|W)', self.text)
        findings['power_rating'] = p_match.group(0) if p_match else None

        # Voltage (V, kV)
        v_match = re.search(r'(\d+(\.\d+)?)\s*(V|kV|Volts)', self.text)
        findings['voltage_rating'] = v_match.group(0) if v_match else None

        # Frequency (Hz, kHz)
        f_match = re.search(r'(\d+(\.\d+)?)\s*(Hz|kHz)', self.text)
        findings['frequency'] = f_match.group(0) if f_match else None

        # Switching Frequency (fsw)
        fsw_match = re.search(r'f_{?sw}?|switching frequency.*?(\d+(\.\d+)?)\s*(kHz|Hz)', self.text, re.IGNORECASE)
        findings['switching_frequency'] = fsw_match.group(0) if fsw_match else None

        # Inductance (L, mH, uH)
        l_match = re.search(r'(\d+(\.\d+)?)\s*(mH|uH|µH|H)', self.text)
        findings['filter_inductance'] = l_match.group(0) if l_match else None

        # Capacitance (C, uF, mF)
        c_match = re.search(r'(\d+(\.\d+)?)\s*(uF|µF|mF|nF)', self.text)
        findings['dc_link_capacitance'] = c_match.group(0) if c_match else None

        # 2. Identify missing parameters and provide smart defaults
        missing_list = []

        if not findings['power_rating']:
            missing_list.append({
                "param": "Rated Power (P)",
                "unit": "kW",
                "default": "5.5",
                "reason": "Required for motor sizing and DC-link calculations."
            })
        if not findings['voltage_rating']:
            missing_list.append({
                "param": "Rated Voltage (V)",
                "unit": "V",
                "default": "415",
                "reason": "Required for 3-phase inverter modulation."
            })
        if not findings['switching_frequency']:
            missing_list.append({
                "param": "Inverter Switching Frequency (fsw)",
                "unit": "kHz",
                "default": "10",
                "reason": "Critical for PWM carrier generator and harmonic filter design."
            })
        if not findings['dc_link_capacitance']:
            missing_list.append({
                "param": "DC Link Capacitance (Cdc)",
                "unit": "µF",
                "default": "1200",
                "reason": "Needed for voltage ripple stabilization."
            })
        if not findings['filter_inductance']:
            missing_list.append({
                "param": "Filter Inductor (Lf)",
                "unit": "mH",
                "default": "2.5",
                "reason": "Needed for current THD suppression under IEEE 519."
            })

        return {
            "detected": {k: v for k, v in findings.items() if v is not None},
            "missing_audit": missing_list,
            "status": "REQUIRES_STUDENT_CONFIRMATION" if missing_list else "READY_FOR_SIMULATION"
        }
