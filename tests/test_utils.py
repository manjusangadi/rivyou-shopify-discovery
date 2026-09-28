"""
Unit tests for domain normalization, deduplication, email validation, and social URL normalization.
"""
import pytest
from src.utils import (
    normalize_domain,
    is_valid_domain,
    is_valid_email,
    normalize_social_url,
    clean_text
)


def test_domain_normalization():
    # Strips protocol, www, trailing slashes, paths, and query parameters
    assert normalize_domain("https://www.example.com/") == "example.com"
    assert normalize_domain("http://example.com") == "example.com"
    assert normalize_domain("https://example.com/about-us?query=1") == "example.com"
    assert normalize_domain("www.snitch.co.in") == "snitch.co.in"
    assert normalize_domain("http://WWW.STORE.IN/") == "store.in"


def test_shopify_subdomain_preservation():
    # CRITICAL: brand1.myshopify.com and brand2.myshopify.com must NOT collapse to myshopify.com
    brand1 = normalize_domain("https://brand1.myshopify.com/")
    brand2 = normalize_domain("https://brand2.myshopify.com/collections")

    assert brand1 == "brand1.myshopify.com"
    assert brand2 == "brand2.myshopify.com"
    assert brand1 != brand2
    assert brand1 != "myshopify.com"


def test_domain_validation():
    assert is_valid_domain("snitch.co.in") is True
    assert is_valid_domain("sugar-cosmetics.myshopify.com") is True
    assert is_valid_domain("indianartvilla.in") is True

    # Rejection of blacklisted / invalid domains
    assert is_valid_domain("myshopify.com") is False
    assert is_valid_domain("facebook.com") is False
    assert is_valid_domain("cdn.shopify.com") is False
    assert is_valid_domain("") is False
    assert is_valid_domain("invalid_domain_without_tld") is False


def test_email_validation():
    assert is_valid_email("support@indianartvilla.in") is True
    assert is_valid_email("hello@brand.co.in") is True
    assert is_valid_email("care@sugarcosmetics.com") is True

    # Reject static asset false positives
    assert is_valid_email("logo@brand.png") is False
    assert is_valid_email("icon@site.svg") is False
    assert is_valid_email("style@site.css") is False

    # Reject version tags (e.g. npm packages)
    assert is_valid_email("bootstrap-icons@1.13.1") is False

    # Reject placeholder dummy emails
    assert is_valid_email("example@example.com") is False
    assert is_valid_email("test@test.com") is False


def test_social_url_normalization():
    # Cleans tracking parameters and trailing slashes
    clean_ig = normalize_social_url("https://www.instagram.com/mybrand/?utm_source=ig_web_copy_link")
    assert clean_ig == "https://instagram.com/mybrand"

    clean_fb = normalize_social_url("http://facebook.com/mybrand?ref=bookmarks")
    assert clean_fb == "https://facebook.com/mybrand"

    # Preserves handle
    clean_tw = normalize_social_url("https://x.com/official_brand/")
    assert clean_tw == "https://x.com/official_brand"

    # Rejects share dialogs and intent links
    assert normalize_social_url("https://www.facebook.com/sharer/sharer.php?u=https://example.com") is None
    assert normalize_social_url("https://twitter.com/intent/tweet?text=hello") is None
    assert normalize_social_url("https://www.linkedin.com/shareArticle?mini=true") is None

    # Rejects platform homepages
    assert normalize_social_url("https://instagram.com/") is None
    assert normalize_social_url("https://facebook.com") is None


def test_clean_text():
    raw = "   \n\t  Handcrafted &amp; Pure Copper Bottles \n  Made in India.   "
    cleaned = clean_text(raw, max_length=100)
    assert cleaned == "Handcrafted & Pure Copper Bottles Made in India."
