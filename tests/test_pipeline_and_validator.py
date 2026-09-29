"""
Unit tests for pipeline active/genuine storefront validation and output validator logic.
"""
from pathlib import Path
import pytest

from src.config import Config
from src.fetch import FetchResult
from src.pipeline import Pipeline
from scripts.validate_output import validate_outputs


@pytest.fixture
def pipeline():
    config = Config()
    return Pipeline(config=config)


def test_password_url_redirect_rejected(pipeline):
    res = FetchResult(
        url="https://testbrand.in",
        status_code=200,
        final_url="https://testbrand.in/password",
        text="<html><body>Enter password to access store</body></html>"
    )
    is_active, reason = pipeline._check_active_and_genuine_store(res, "testbrand.in")
    assert is_active is False
    assert "password" in reason.lower()


def test_password_template_in_html_rejected(pipeline):
    res = FetchResult(
        url="https://secretbrand.in",
        status_code=200,
        final_url="https://secretbrand.in",
        text="<html><body class='template-password'><form id='login_form' action='/password'></form></body></html>"
    )
    is_active, reason = pipeline._check_active_and_genuine_store(res, "secretbrand.in")
    assert is_active is False
    assert "password" in reason.lower()


def test_opening_soon_page_rejected(pipeline):
    res = FetchResult(
        url="https://comingsoonbrand.in",
        status_code=200,
        final_url="https://comingsoonbrand.in",
        text="<html><head><title>Opening Soon</title></head><body><h1>Our store will be opening soon</h1><p>Be the first to know</p></body></html>"
    )
    is_active, reason = pipeline._check_active_and_genuine_store(res, "comingsoonbrand.in")
    assert is_active is False
    assert "opening soon" in reason.lower()


def test_parked_domain_rejected(pipeline):
    res = FetchResult(
        url="https://parkedstore.in",
        status_code=200,
        final_url="https://parkedstore.in",
        text="<html><body><h1>This domain is parked, courtesy of GoDaddy.com</h1><p>Buy this domain today</p></body></html>"
    )
    is_active, reason = pipeline._check_active_and_genuine_store(res, "parkedstore.in")
    assert is_active is False
    assert "parked" in reason.lower()


def test_demo_theme_boilerplate_rejected(pipeline):
    res = FetchResult(
        url="https://dev-shop-test.myshopify.com",
        status_code=200,
        final_url="https://dev-shop-test.myshopify.com",
        text="<html><body><p>Write a few sentences to tell people about your store</p><p>Use this text to share information about your brand</p></body></html>"
    )
    is_active, reason = pipeline._check_active_and_genuine_store(res, "dev-shop-test.myshopify.com")
    assert is_active is False
    assert "boilerplate" in reason.lower() or "demo" in reason.lower()


def test_genuine_active_store_accepted(pipeline):
    res = FetchResult(
        url="https://snitch.co.in",
        status_code=200,
        final_url="https://snitch.co.in",
        text="<html><body><h1>Snitch Men's Fashion</h1><p>Explore luxury menswear online. 100% genuine products.</p></body></html>"
    )
    is_active, reason = pipeline._check_active_and_genuine_store(res, "snitch.co.in")
    assert is_active is True
    assert reason is None


def test_validator_detects_count_mismatch(tmp_path):
    csv_file = tmp_path / "stores.csv"
    audit_file = tmp_path / "audit.csv"
    summary_file = tmp_path / "summary.json"

    # Write CSV with 2 rows
    csv_file.write_text(
        "domain_url,all_contacts,socials,category,tagline_description,logo,state\n"
        "https://store1.in,support@store1.in,https://instagram.com/s1,apparel & fashion,Best clothing,https://store1.in/logo.png,Karnataka\n"
        "https://store2.in,support@store2.in,https://instagram.com/s2,beauty & skincare,Clean skincare,https://store2.in/logo.png,Maharashtra\n",
        encoding="utf-8"
    )
    audit_file.write_text("domain_url,final_decision\nhttps://store1.in,ACCEPTED\nhttps://store2.in,ACCEPTED\n", encoding="utf-8")

    # Write summary with 3 rows (mismatch)
    summary_file.write_text(
        '{"final_stores": 3, "email_coverage": 1.0, "phone_coverage": 0.0, "social_coverage": 1.0, "state_coverage": 1.0, "logo_coverage": 1.0}',
        encoding="utf-8"
    )

    ok = validate_outputs(stores_path=csv_file, audit_path=audit_file, summary_path=summary_file)
    assert ok is False


def test_validator_accepts_other_as_unclassified_category(tmp_path):
    csv_file = tmp_path / "stores.csv"
    audit_file = tmp_path / "audit.csv"
    summary_file = tmp_path / "summary.json"

    # Write CSV where one category is "other" and one is "fashion"
    csv_file.write_text(
        "domain_url,all_contacts,socials,category,tagline_description,logo,state\n"
        "https://store1.in,support@store1.in,https://instagram.com/s1,apparel & fashion,Best clothing,https://store1.in/logo.png,Karnataka\n"
        "https://store2.in,support@store2.in,https://instagram.com/s2,other,General store,https://store2.in/logo.png,Maharashtra\n",
        encoding="utf-8"
    )
    audit_file.write_text("domain_url,final_decision\nhttps://store1.in,ACCEPTED\nhttps://store2.in,ACCEPTED\n", encoding="utf-8")

    summary_file.write_text(
        '{"final_stores": 2, "email_coverage": 1.0, "phone_coverage": 0.0, "social_coverage": 1.0, "state_coverage": 1.0, "logo_coverage": 1.0}',
        encoding="utf-8"
    )

    ok = validate_outputs(stores_path=csv_file, audit_path=audit_file, summary_path=summary_file)
    assert ok is True


def test_validator_detects_coverage_mismatch(tmp_path):
    csv_file = tmp_path / "stores.csv"
    audit_file = tmp_path / "audit.csv"
    summary_file = tmp_path / "summary.json"

    # 2 rows, both have emails (actual email cov = 1.0)
    csv_file.write_text(
        "domain_url,all_contacts,socials,category,tagline_description,logo,state\n"
        "https://store1.in,support@store1.in,https://instagram.com/s1,apparel & fashion,Best clothing,https://store1.in/logo.png,Karnataka\n"
        "https://store2.in,support@store2.in,https://instagram.com/s2,beauty & skincare,Clean skincare,https://store2.in/logo.png,Maharashtra\n",
        encoding="utf-8"
    )
    audit_file.write_text("domain_url,final_decision\nhttps://store1.in,ACCEPTED\nhttps://store2.in,ACCEPTED\n", encoding="utf-8")

    # Summary claims email_coverage is 0.5 (diff = 0.5 > 0.005)
    summary_file.write_text(
        '{"final_stores": 2, "email_coverage": 0.5, "phone_coverage": 0.0, "social_coverage": 1.0, "state_coverage": 1.0, "logo_coverage": 1.0}',
        encoding="utf-8"
    )

    ok = validate_outputs(stores_path=csv_file, audit_path=audit_file, summary_path=summary_file)
    assert ok is False
