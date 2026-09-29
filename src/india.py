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

# India Post 2-digit PIN code prefix to State mapping
PIN_PREFIX_TO_STATE: Dict[str, str] = {
    "11": "Delhi",
    "12": "Haryana", "13": "Haryana",
    "14": "Punjab", "15": "Punjab",
    "16": "Chandigarh",
    "17": "Himachal Pradesh",
    "18": "Jammu and Kashmir", "19": "Jammu and Kashmir",
    "20": "Uttar Pradesh", "21": "Uttar Pradesh", "22": "Uttar Pradesh",
    "23": "Uttar Pradesh", "24": "Uttar Pradesh", "25": "Uttar Pradesh",
    "26": "Uttar Pradesh", "27": "Uttar Pradesh", "28": "Uttar Pradesh",
    "30": "Rajasthan", "31": "Rajasthan", "32": "Rajasthan", "33": "Rajasthan", "34": "Rajasthan",
    "36": "Gujarat", "37": "Gujarat", "38": "Gujarat", "39": "Gujarat",
    "41": "Maharashtra", "42": "Maharashtra", "43": "Maharashtra", "44": "Maharashtra",
    "45": "Madhya Pradesh", "46": "Madhya Pradesh", "47": "Madhya Pradesh", "48": "Madhya Pradesh",
    "49": "Chhattisgarh",
    "50": "Telangana",
    "51": "Andhra Pradesh", "52": "Andhra Pradesh", "53": "Andhra Pradesh",
    "56": "Karnataka", "57": "Karnataka", "58": "Karnataka", "59": "Karnataka",
    "60": "Tamil Nadu", "61": "Tamil Nadu", "62": "Tamil Nadu", "63": "Tamil Nadu", "64": "Tamil Nadu",
    "67": "Kerala", "68": "Kerala", "69": "Kerala",
    "70": "West Bengal", "71": "West Bengal", "72": "West Bengal", "73": "West Bengal", "74": "West Bengal",
    "75": "Odisha", "76": "Odisha", "77": "Odisha",
    "78": "Assam",
    "80": "Bihar", "81": "Bihar", "82": "Bihar",
    "83": "Jharkhand",
    "84": "Bihar", "85": "Bihar",
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

    def _state_from_pin(self, pin: str) -> Optional[str]:
        """Maps a 6-digit Indian PIN code to its canonical State / Union Territory."""
        if not pin or len(pin) != 6 or not pin.isdigit():
            return None
        prefix3 = pin[:3]
        if prefix3 in {"400", "401", "402"}:
            return "Maharashtra"
        if prefix3 == "403":
            return "Goa"
        if prefix3 in {"248", "249"}:
            return "Uttarakhand"
        if prefix3 == "605":
            return "Puducherry"
        prefix2 = pin[:2]
        return PIN_PREFIX_TO_STATE.get(prefix2)

    def _validate_gstin(self, candidate: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validates a candidate GSTIN string:
        - Must be exactly 15 characters matching standard Indian GSTIN structure.
        - First 2 digits must map to a valid Indian state/UT code in GST_STATE_CODES.
        - Filters out known dummy/placeholder sequences.
        Returns: (is_valid, state_name, state_code)
        """
        if not candidate or len(candidate) != 15:
            return False, None, None

        cand_upper = candidate.strip().upper()
        # Standard structure: 2 digits + 5 letters (PAN) + 4 digits + 1 letter + 1 entity char + 'Z' + 1 check char
        pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
        if not re.match(pattern, cand_upper):
            return False, None, None

        st_code = cand_upper[:2]
        gst_state = GST_STATE_CODES.get(st_code)
        if not gst_state:
            return False, None, None

        # Filter out clearly invalid / dummy repeating sequences
        if len(set(cand_upper)) <= 3:
            return False, None, None

        return True, gst_state, st_code

    def _is_shipping_text(self, text_snippet: str) -> bool:
        """Identifies text that merely mentions delivery/shipping destinations rather than office location."""
        lower = text_snippet.lower()
        shipping_triggers = [
            "we ship", "ships to", "shipping to", "ship across",
            "we deliver", "delivery to", "delivering to", "deliver all across",
            "delivery across", "available across", "pan india", "cash on delivery",
            "cod available in", "orders delivered to", "free shipping", "shipping available in"
        ]
        return any(trig in lower for trig in shipping_triggers)

    def _extract_address_blocks(self, html_content: str, full_text: str) -> List[str]:
        """
        Extracts high-confidence address and contact blocks from HTML and text,
        filtering out marketing/shipping snippets.
        """
        address_blocks = []
        if html_content:
            try:
                soup = BeautifulSoup(html_content, "lxml")
                # 1. <address> tags
                for addr_tag in soup.find_all("address"):
                    t = addr_tag.get_text(separator=" ", strip=True)
                    if t and not self._is_shipping_text(t):
                        address_blocks.append(t)

                # 2. Specific class / id elements
                for el in soup.find_all(True, class_=re.compile(r"(?:address|contact|footer|location|headquarter|office)", re.I)):
                    t = el.get_text(separator=" ", strip=True)
                    if 15 < len(t) < 800 and not self._is_shipping_text(t):
                        address_blocks.append(t)
            except Exception:
                pass

        # 3. Text regex extraction for office/address prefixes
        text_patterns = [
            r"(?:registered\s+office|head\s+office|corporate\s+office|branch\s+office|our\s+office|factory\s+address|office\s+address|contact\s+us|reach\s+us)[\s\:\-]{1,5}[^\n\r\.]{10,250}",
            r"(?:pin(?:code)?[\s\:\-]*|postal\s+code[\s\:\-]*)[1-8][0-9]{5}[^\n\r\.]{0,100}",
            r"\b[A-Za-z0-9\s,\-\/]{5,60}(?:street|road|nagar|marg|complex|plaza|building|floor|cross|layout|phase|sector|colony|bazaar|industrial\s+area)[A-Za-z0-9\s,\-\/]{5,80}(?:[1-8][0-9]{5})?"
        ]
        for pat in text_patterns:
            for m in re.finditer(pat, full_text, re.IGNORECASE):
                chunk = m.group(0).strip()
                if not self._is_shipping_text(chunk):
                    address_blocks.append(chunk)

        return address_blocks

    def verify(
        self,
        domain: str,
        html_content: str,
        all_pages_text: Optional[str] = None
    ) -> IndiaVerification:
        score = 0
        signals: List[str] = []
        strong_location_signals: List[str] = []
        state: Optional[str] = None
        state_source: Optional[str] = None
        details: Dict[str, Any] = {}

        full_text = f"{html_content} {all_pages_text or ''}"
        text_lower = full_text.lower()
        address_blocks = self._extract_address_blocks(html_content, full_text)
        address_text_combined = " ".join(address_blocks).lower()

        # -------------------------------------------------------------
        # Hierarchy Tier 1: GSTIN Match & State Code (Highest Confidence)
        # -------------------------------------------------------------
        for m in re.finditer(r"\b([0-9]{2}[A-Za-z]{5}[0-9]{4}[A-Za-z][1-9A-Za-z][zZ][0-9A-Za-z])\b", full_text):
            candidate = m.group(1).upper()
            is_valid, gst_state, st_code = self._validate_gstin(candidate)
            if is_valid and gst_state and st_code:
                score += 8
                signals.append(f"gstin:{candidate}")
                strong_location_signals.append("gstin")
                if not state:
                    state = gst_state
                    state_source = f"gstin_code_{st_code}"
                break

        # -------------------------------------------------------------
        # Hierarchy Tier 2: JSON-LD Structured PostalAddress
        # -------------------------------------------------------------
        json_ld_state, json_ld_country = self._extract_jsonld_address(html_content)
        if json_ld_country and ("india" in json_ld_country.lower() or json_ld_country.upper() in {"IN", "IND"}):
            score += 8
            signals.append("jsonld_india_address")
            strong_location_signals.append("jsonld_address")
            if json_ld_state:
                matched_state = self.normalize_state(json_ld_state)
                if matched_state:
                    score += 6
                    signals.append(f"state:{matched_state}")
                    if not state:
                        state = matched_state
                        state_source = "json_ld_address"

        # -------------------------------------------------------------
        # Hierarchy Tier 3: Explicit State in Business / Contact Address
        # -------------------------------------------------------------
        if address_blocks:
            addr_state = self._detect_state_in_text(address_text_combined)
            if addr_state:
                score += 6
                signals.append(f"address_state:{addr_state}")
                strong_location_signals.append("address_state")
                if not state:
                    state = addr_state
                    state_source = "address_state"

        # -------------------------------------------------------------
        # Hierarchy Tier 4: Validated PIN Code in Address Context
        # -------------------------------------------------------------
        pin_match = None
        if address_blocks:
            pin_match = re.search(r"(?:pin(?:code)?[\s\:\-]*|india[\s,.-]*|\b)([1-8][0-9]{5})\b", address_text_combined, re.IGNORECASE)

        if not pin_match:
            pin_near_addr = re.search(r"(?:registered\s+office|head\s+office|corporate\s+office|pincode[\s\:\-]*|pin[\s\:\-]*|postcode[\s\:\-]*)[\w\s,.-]{0,40}(\b[1-8][0-9]{5}\b)", full_text, re.IGNORECASE)
            if pin_near_addr and not self._is_shipping_text(pin_near_addr.group(0)):
                pin_match = pin_near_addr

        if pin_match:
            pin_val = pin_match.group(1)
            derived_state = self._state_from_pin(pin_val)
            if derived_state and len(set(pin_val)) > 1 and pin_val != "123456":
                score += 5
                signals.append(f"address_pin:{pin_val}")
                strong_location_signals.append("address_pincode")
                if not state:
                    state = derived_state
                    state_source = f"pin_code_{pin_val}"

        # -------------------------------------------------------------
        # Hierarchy Tier 5: City in Address Context
        # -------------------------------------------------------------
        if address_blocks:
            city_found, city_state = self._detect_city(address_text_combined)
            if city_found:
                score += 4
                signals.append(f"address_city:{city_found}")
                strong_location_signals.append("address_city")
                if not state:
                    state = city_state
                    state_source = f"address_city_{city_found}"

        # -------------------------------------------------------------
        # Supporting Signals (Contribute to score, but CANNOT verify alone)
        # -------------------------------------------------------------
        # Phone (+91)
        if re.search(r"(?:\+91[\s\-]?)?[6-9]\d{9}\b", full_text) or "+91" in full_text:
            if "+91" in full_text or "tel:+91" in full_text or "91-" in full_text:
                score += 5
                signals.append("phone:+91")

        # Payment Gateways (Razorpay, Cashfree, UPI, etc.)
        payment_signals = []
        if any(g in text_lower for g in ["razorpay", "cashfree", "payu", "paytm", "phonepe", "upi", "bhim"]):
            payment_signals.append("indian_payment_gateway")
        if payment_signals:
            score += 3
            signals.extend(payment_signals)

        # Currency (INR, ₹, Rs.)
        if "₹" in full_text or "inr" in text_lower or "rs." in text_lower or "rupees" in text_lower:
            score += 2
            signals.append("currency:INR")

        # Domain TLD
        if domain.endswith(".co.in"):
            score += 2
            signals.append("domain:.co.in")
        elif domain.endswith(".in"):
            score += 1
            signals.append("domain:.in")

        # Isolated city mention outside address block (Supporting score only, NEVER establishes state)
        if not address_blocks or "address_city" not in strong_location_signals:
            iso_city, _ = self._detect_city(text_lower)
            if iso_city and not self._is_shipping_text(text_lower):
                score += 2
                signals.append(f"city_mention:{iso_city}")

        # -------------------------------------------------------------
        # Final Verification Determination
        # -------------------------------------------------------------
        has_strong_location = len(strong_location_signals) > 0
        is_india = (score >= self.threshold) and has_strong_location

        # If state could not be established with high confidence, leave empty
        if not state:
            state = ""
            state_source = ""

        details = {
            "score": score,
            "signals": signals,
            "strong_location_signals": strong_location_signals,
            "has_strong_location": has_strong_location,
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
