"""
Unit tests for India verification, state extraction, and false positive prevention.
"""
import pytest
from src.india import IndiaVerifier, CANONICAL_STATES_AND_UTS


@pytest.fixture
def verifier():
    return IndiaVerifier(threshold=7)


def test_canonical_states_list():
    assert len(CANONICAL_STATES_AND_UTS) == 36
    assert "Karnataka" in CANONICAL_STATES_AND_UTS
    assert "Maharashtra" in CANONICAL_STATES_AND_UTS
    assert "Tamil Nadu" in CANONICAL_STATES_AND_UTS
    assert "Delhi" in CANONICAL_STATES_AND_UTS
    assert "Gujarat" in CANONICAL_STATES_AND_UTS


def test_state_abbreviation_normalization(verifier):
    assert verifier.normalize_state("KA") == "Karnataka"
    assert verifier.normalize_state("MH") == "Maharashtra"
    assert verifier.normalize_state("TN") == "Tamil Nadu"
    assert verifier.normalize_state("DL") == "Delhi"
    assert verifier.normalize_state("GJ") == "Gujarat"
    assert verifier.normalize_state("WB") == "West Bengal"


def test_jsonld_address_detection(verifier):
    html = """
    <html>
    <head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "Indian Brand",
        "address": {
          "@type": "PostalAddress",
          "streetAddress": "100ft Road, Indiranagar",
          "addressLocality": "Bengaluru",
          "addressRegion": "Karnataka",
          "postalCode": "560038",
          "addressCountry": "India"
        }
      }
      </script>
    </head>
    <body>Welcome to our Indian store</body>
    </html>
    """
    ver = verifier.verify(domain="brand.in", html_content=html)
    assert ver.is_india is True
    assert ver.score >= 14
    assert ver.state == "Karnataka"
    assert "jsonld_india_address" in ver.signals
    assert "state:Karnataka" in ver.signals


def test_gstin_and_state_derivation(verifier):
    # GSTIN starting with 27 is Maharashtra
    html = """
    <html>
    <body>
      <footer>
        <p>Company: Mumbai D2C Retail Pvt Ltd</p>
        <p>GSTIN: 27AABCM1234F1Z9</p>
        <p>Phone: +91 98765 43210</p>
      </footer>
    </body>
    </html>
    """
    ver = verifier.verify(domain="mumbaibrand.com", html_content=html)
    assert ver.is_india is True
    assert ver.score >= 11
    assert ver.state == "Maharashtra"
    assert "gstin:27AABCM1234F1Z9" in ver.signals
    assert "phone:+91" in ver.signals


def test_pin_code_and_city_detection(verifier):
    html = """
    <html>
    <body>
      <p>Visit our showroom in Jaipur, Rajasthan. Pincode: 302001. Support in INR.</p>
    </body>
    </html>
    """
    ver = verifier.verify(domain="jaipurcrafts.com", html_content=html)
    assert ver.is_india is True
    assert ver.state == "Rajasthan"
    assert any("302001" in s for s in ver.signals)
    assert any("jaipur" in s for s in ver.signals)


def test_false_positive_rejected(verifier):
    # A store having only .in domain and currency symbol ₹ should NOT pass threshold of 7
    html = """
    <html>
    <head><title>Global Drop-shipper</title></head>
    <body>
      <p>Worldwide shipping available! Price: ₹1,500</p>
    </body>
    </html>
    """
    # .in (1) + currency:INR (2) = 3 points (threshold is 7)
    ver = verifier.verify(domain="dropshipstore.in", html_content=html)
    assert ver.is_india is False
    assert ver.score < 7


def test_phone_and_currency_alone_fails_india_verification(verifier):
    """
    Mandatory rule: +91 phone (5 pts) and INR (2 pts) gives score 7,
    but must NOT verify India without at least one strong location signal.
    """
    html = """
    <html>
    <body>
      <h1>International Boutique</h1>
      <p>Call our support line: +91 98765 43210</p>
      <p>All prices listed in INR (₹)</p>
    </body>
    </html>
    """
    ver = verifier.verify(domain="internationalboutique.com", html_content=html)
    assert ver.score >= 7
    assert ver.is_india is False  # Fails because no strong location evidence is present
    assert len(ver.details.get("strong_location_signals", [])) == 0


def test_pin_without_address_context_does_not_verify_india(verifier):
    """
    A 6-digit number appearing in product specs or SKU outside address context
    must NOT count as strong location evidence.
    """
    html = """
    <html>
    <body>
      <h1>Electronics Shop</h1>
      <p>Product SKU: 560038. Order number: 987654.</p>
      <p>Support: +91 99999 88888</p>
    </body>
    </html>
    """
    ver = verifier.verify(domain="electronicstore.com", html_content=html)
    assert "address_pincode" not in ver.details.get("strong_location_signals", [])
    assert ver.is_india is False


def test_city_in_shipping_text_does_not_set_state(verifier):
    """
    City names appearing strictly in delivery or shipping marketing copy
    must NOT establish the business state.
    """
    html = """
    <html>
    <body>
      <h1>Global Apparel</h1>
      <p>We deliver fast to Bengaluru, Mumbai, and Delhi! Free shipping all across India.</p>
      <p>Prices in INR: ₹2,499</p>
    </body>
    </html>
    """
    ver = verifier.verify(domain="globalapparel.com", html_content=html)
    assert ver.state == ""
    assert ver.state_source == ""
    assert ver.is_india is False


def test_gstin_state_mapping_for_multiple_states(verifier):
    """
    Verify GSTIN state code derivations:
    27 -> Maharashtra
    29 -> Karnataka
    07 -> Delhi
    33 -> Tamil Nadu
    36 -> Telangana
    """
    test_cases = [
        ("27AAAAA0000A1Z5", "Maharashtra"),
        ("29BBBBB1111B1Z6", "Karnataka"),
        ("07CCCCC2222C1Z7", "Delhi"),
        ("33DDDDD3333D1Z8", "Tamil Nadu"),
        ("36EEEEE4444E1Z9", "Telangana"),
    ]
    for gstin, expected_state in test_cases:
        html = f"<html><body><p>Registered Office: GSTIN: {gstin}</p></body></html>"
        ver = verifier.verify(domain="gstintest.com", html_content=html)
        assert ver.is_india is True
        assert ver.state == expected_state
        assert "gstin" in ver.details.get("strong_location_signals", [])


def test_gstin_validation_regression(verifier):
    """
    Regression tests for strengthened GSTIN validation:
    - valid GSTIN with state code 27 -> Maharashtra
    - valid GSTIN with state code 29 -> Karnataka
    - invalid GSTIN format -> rejected
    - invalid/unknown GST state code -> rejected as GST evidence
    """
    # 1. Valid GSTIN with state code 27 -> Maharashtra
    html_mh = "<html><body><p>Registered Office: GSTIN: 27AABCM1234F1Z9</p></body></html>"
    ver_mh = verifier.verify(domain="mh-brand.com", html_content=html_mh)
    assert ver_mh.is_india is True
    assert ver_mh.state == "Maharashtra"
    assert "gstin" in ver_mh.details.get("strong_location_signals", [])

    # 2. Valid GSTIN with state code 29 -> Karnataka
    html_ka = "<html><body><p>Corporate Office: GSTIN: 29AABCM1234F1Z9</p></body></html>"
    ver_ka = verifier.verify(domain="ka-brand.com", html_content=html_ka)
    assert ver_ka.is_india is True
    assert ver_ka.state == "Karnataka"
    assert "gstin" in ver_ka.details.get("strong_location_signals", [])

    # 3. Invalid GSTIN format -> rejected
    html_bad_fmt = "<html><body><p>GSTIN: INVALID_GST_12345</p><p>GSTIN: 271234567890123</p></body></html>"
    ver_bad_fmt = verifier.verify(domain="badformat.com", html_content=html_bad_fmt)
    assert "gstin" not in ver_bad_fmt.details.get("strong_location_signals", [])
    assert ver_bad_fmt.is_india is False

    # 4. Invalid/unknown GST state code -> rejected as GST evidence
    # State codes 99, 00, 28 are not valid GST state codes
    html_bad_code = "<html><body><p>GSTIN: 99AABCM1234F1Z9</p><p>GSTIN: 00AABCM1234F1Z9</p></body></html>"
    ver_bad_code = verifier.verify(domain="badcode.com", html_content=html_bad_code)
    assert "gstin" not in ver_bad_code.details.get("strong_location_signals", [])
    assert ver_bad_code.is_india is False
    assert ver_bad_code.state == ""

