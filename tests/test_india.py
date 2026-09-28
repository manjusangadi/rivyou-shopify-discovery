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
    assert any("pin_code:302001" in s for s in ver.signals)
    assert any("city:jaipur" in s for s in ver.signals)


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
