"""
India verification and canonical Indian state extraction engine.
"""
import json
import logging
import re
from typing import Dict, List, Optional, Tuple, Set, Any
from bs4 import BeautifulSoup

from src.models import IndiaVerification

logger = logging.getLogger(__name__)

# Canonical list of all 28 States and 8 Union Territories in India
CANONICAL_STATES_AND_UTS = {
    # 28 States
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
    # 8 Union Territories
    "Andaman and Nicobar Islands",
    "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Jammu and Kashmir",
    "Ladakh",
    "Lakshadweep",
    "Puducherry",
}

# Standard 2-letter state abbreviations to canonical name mapping
STATE_ABBREVIATIONS: Dict[str, str] = {
    "AP": "Andhra Pradesh",
    "AR": "Arunachal Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CG": "Chhattisgarh",
    "CH": "Chandigarh",
    "DL": "Delhi",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HR": "Haryana",
    "HP": "Himachal Pradesh",
    "JH": "Jharkhand",
    "JK": "Jammu and Kashmir",
    "KA": "Karnataka",
    "KL": "Kerala",
    "LA": "Ladakh",
    "LD": "Lakshadweep",
    "MP": "Madhya Pradesh",
    "MH": "Maharashtra",
    "MN": "Manipur",
    "ML": "Meghalaya",
    "MZ": "Mizoram",
    "NL": "Nagaland",
    "OD": "Odisha",
    "OR": "Odisha",
    "PB": "Punjab",
    "PY": "Puducherry",
    "RJ": "Rajasthan",
    "SK": "Sikkim",
    "TN": "Tamil Nadu",
    "TG": "Telangana",
    "TS": "Telangana",
    "TR": "Tripura",
    "UP": "Uttar Pradesh",
    "UK": "Uttarakhand",
    "UA": "Uttarakhand",
    "WB": "West Bengal",
    "AN": "Andaman and Nicobar Islands",
    "DN": "Dadra and Nagar Haveli and Daman and Diu",
    "DD": "Dadra and Nagar Haveli and Daman and Diu",
}

# GST State Code Mapping (first 2 digits of GSTIN)
GST_STATE_CODES: Dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
}

# Major Indian Cities mapped to State
MAJOR_INDIAN_CITIES: Dict[str, str] = {
    "bengaluru": "Karnataka",
    "bangalore": "Karnataka",
    "mumbai": "Maharashtra",
    "pune": "Maharashtra",
    "nagpur": "Maharashtra",
    "thane": "Maharashtra",
    "navi mumbai": "Maharashtra",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "noida": "Uttar Pradesh",
    "greater noida": "Uttar Pradesh",
    "gurgaon": "Haryana",
    "gurugram": "Haryana",
    "faridabad": "Haryana",
    "hyderabad": "Telangana",
    "secunderabad": "Telangana",
    "chennai": "Tamil Nadu",
    "coimbatore": "Tamil Nadu",
    "madurai": "Tamil Nadu",
    "kolkata": "West Bengal",
    "ahmedabad": "Gujarat",
    "surat": "Gujarat",
    "vadodara": "Gujarat",
    "rajkot": "Gujarat",
    "jaipur": "Rajasthan",
    "jodhpur": "Rajasthan",
    "udaipur": "Rajasthan",
    "lucknow": "Uttar Pradesh",
    "kanpur": "Uttar Pradesh",
    "agra": "Uttar Pradesh",
    "varanasi": "Uttar Pradesh",
    "indore": "Madhya Pradesh",
    "bhopal": "Madhya Pradesh",
    "chandigarh": "Chandigarh",
    "amritsar": "Punjab",
    "ludhiana": "Punjab",
    "kochi": "Kerala",
    "cochin": "Kerala",
    "thiruvananthapuram": "Kerala",
    "trivandrum": "Kerala",
    "kozhikode": "Kerala",
    "bhubaneswar": "Odisha",
    "cuttack": "Odisha",
    "patna": "Bihar",
    "ranchi": "Jharkhand",
    "raipur": "Chhattisgarh",
    "dehradun": "Uttarakhand",
    "guwahati": "Assam",
    "panaji": "Goa",
    "visakhapatnam": "Andhra Pradesh",
    "vijayawada": "Andhra Pradesh",
}


class IndiaVerifier:
    """
    Verifies that a storefront is an authentic India-based business.
    Calculates an India score from multi-layered geographic, commercial,
    contact, and structured metadata signals.
    """

    def __init__(self, threshold: int = 7):
        self.threshold = threshold

    def normalize_state(self, state_str: str) -> Optional[str]:
        """Matches a raw state name or abbreviation to canonical state string."""
        if not state_str:
            return None

        clean = state_str.strip().title()

        # Direct canonical match
        for s in CANONICAL_STATES_AND_UTS:
            if clean.lower() == s.lower():
                return s

        # Abbreviation match (e.g. KA, MH, DL)
        upper = state_str.strip().upper()
        if upper in STATE_ABBREVIATIONS:
            return STATE_ABBREVIATIONS[upper]

        # Partial / alias matches
        clean_lower = clean.lower()
        if "delhi" in clean_lower or "nct" in clean_lower:
            return "Delhi"
        if "orissa" in clean_lower:
            return "Odisha"
        if "pondicherry" in clean_lower:
            return "Puducherry"
        if "kashmir" in clean_lower or "jammu" in clean_lower:
            return "Jammu and Kashmir"
        if "daman" in clean_lower or "diu" in clean_lower or "dadra" in clean_lower:
            return "Dadra and Nagar Haveli and Daman and Diu"

        return None

    def verify(
        self,
        domain: str,
        html_content: str,
        all_pages_text: Optional[str] = None
    ) -> IndiaVerification:
        score = 0
        signals: List[str] = []
        state: Optional[str] = None
        state_source: Optional[str] = None
        details: Dict[str, Any] = {}

        full_text = f"{html_content} {all_pages_text or ''}"
        text_lower = full_text.lower()

        # 1. Domain TLD Signals
        if domain.endswith(".co.in"):
            score += 2
            signals.append("domain:.co.in")
        elif domain.endswith(".in"):
            score += 1
            signals.append("domain:.in")

        # 2. JSON-LD Structured PostalAddress
        json_ld_state, json_ld_country = self._extract_jsonld_address(html_content)
        if json_ld_country and ("india" in json_ld_country.lower() or json_ld_country.upper() in {"IN", "IND"}):
            score += 8
            signals.append("jsonld_india_address")
            if json_ld_state:
                matched_state = self.normalize_state(json_ld_state)
                if matched_state:
                    state = matched_state
                    state_source = "json_ld_address"
                    score += 6
                    signals.append(f"state:{matched_state}")

        # 3. GSTIN Detection (15-character Indian Goods & Services Tax Number)
        # Format: 2 digits (State Code) + 5 alpha (PAN) + 4 numeric + 1 alpha + 1 entity + 'Z' + 1 check digit
        gstin_match = re.search(r"\b([0-3][0-9])[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}\b", full_text)
        if gstin_match:
            st_code = gstin_match.group(1)
            gst_state = GST_STATE_CODES.get(st_code)
            score += 6
            signals.append(f"gstin:{gstin_match.group(0)}")
            if gst_state and not state:
                state = gst_state
                state_source = f"gstin_code_{st_code}"

        # 4. Indian Phone Number (+91 prefix or Indian mobile format)
        if re.search(r"(?:\+91[\s\-]?)?[6-9]\d{9}\b", full_text) or "+91" in full_text:
            # Check specifically for +91 or tel:+91
            if "+91" in full_text or "tel:+91" in full_text or "91-" in full_text:
                score += 5
                signals.append("phone:+91")

        # 5. Indian PIN code (6 digits, starting 1-8)
        # Ensure it is near state/city keywords or "pincode", "pin", "india" to avoid false matches
        pin_match = re.search(r"(?:pin(?:code)?[\s:]*|india[\s,.-]*)(\b[1-8][0-9]{5}\b)", full_text, re.IGNORECASE)
        if not pin_match:
            # Look for 6-digit number following state or city
            pin_match = re.search(r"(?:delhi|mumbai|bengaluru|bangalore|chennai|hyderabad|pune|ahmedabad|jaipur|kolkata|karnataka|maharashtra|tamil nadu|gujarat)[\s,.-]*(\b[1-8][0-9]{5}\b)", full_text, re.IGNORECASE)

        if pin_match:
            score += 5
            signals.append(f"pin_code:{pin_match.group(1)}")

        # 6. Indian City detection
        city_found, city_state = self._detect_city(text_lower)
        if city_found:
            score += 4
            signals.append(f"city:{city_found}")
            if city_state and not state:
                state = city_state
                state_source = f"city_{city_found}"

        # 7. Indian State mentioned directly in text
        if not state:
            matched_state = self._detect_state_in_text(text_lower)
            if matched_state:
                state = matched_state
                state_source = "text_mention"
                score += 6
                signals.append(f"state:{matched_state}")

        # 8. Indian Payment Gateways & UPI
        payment_signals = []
        if any(g in text_lower for g in ["razorpay", "cashfree", "payu", "paytm", "phonepe", "upi", "bhim"]):
            payment_signals.append("indian_payment_gateway")
        if payment_signals:
            score += 3
            signals.extend(payment_signals)

        # 9. Currency Signals (INR, ₹, Rs.)
        if "₹" in full_text or "inr" in text_lower or "rs." in text_lower or "rupees" in text_lower:
            score += 2
            signals.append("currency:INR")

        is_india = score >= self.threshold
        details = {
            "score": score,
            "signals": signals,
            "state": state,
            "state_source": state_source,
            "threshold": self.threshold
        }

        return IndiaVerification(
            is_india=is_india,
            score=score,
            signals=signals,
            state=state,
            state_source=state_source,
            details=details
        )

    def _extract_jsonld_address(self, html: str) -> Tuple[Optional[str], Optional[str]]:
        """Parses JSON-LD blocks for PostalAddress schema."""
        if not html:
            return None, None

        state, country = None, None
        try:
            soup = BeautifulSoup(html, "lxml")
            scripts = soup.find_all("script", type="application/ld+json")
            for script in scripts:
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string.strip())
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        # Direct or graph traversal
                        candidates = [item]
                        if "@graph" in item and isinstance(item["@graph"], list):
                            candidates.extend(item["@graph"])

                        for c in candidates:
                            addr = c.get("address")
                            if isinstance(addr, dict):
                                st = addr.get("addressRegion") or addr.get("addressLocality")
                                ct = addr.get("addressCountry")
                                if isinstance(ct, dict):
                                    ct = ct.get("name")
                                if ct:
                                    country = str(ct)
                                if st:
                                    state = str(st)
                                if country:
                                    return state, country
                except Exception:
                    continue
        except Exception:
            pass

        return state, country

    def _detect_city(self, text_lower: str) -> Tuple[Optional[str], Optional[str]]:
        """Detects notable Indian cities mentioned in business contact context."""
        for city, st in MAJOR_INDIAN_CITIES.items():
            pattern = rf"\b{re.escape(city)}\b"
            if re.search(pattern, text_lower):
                return city, st
        return None, None

    def _detect_state_in_text(self, text_lower: str) -> Optional[str]:
        """Detects canonical Indian state names mentioned in text."""
        # Check longer names first to avoid sub-word overlap
        sorted_states = sorted(CANONICAL_STATES_AND_UTS, key=lambda s: len(s), reverse=True)
        for st in sorted_states:
            pattern = rf"\b{re.escape(st.lower())}\b"
            if re.search(pattern, text_lower):
                return st
        return None
