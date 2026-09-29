"""
Unit tests for data extraction (emails, phones, socials, categories, descriptions, logos).
"""
import pytest
from src.extract import DataExtractor


@pytest.fixture
def extractor():
    return DataExtractor()


def test_email_extraction(extractor):
    html = """
    <html>
    <body>
      <a href="mailto:support@snitch.co.in">Contact Support</a>
      <p>For sales inquiries reach out to sales@snitch.co.in</p>
      <!-- False positives to reject -->
      <img src="banner@2x.png">
      <span>version: bootstrap-icons@1.13.1</span>
      <p>test@test.com</p>
    </body>
    </html>
    """
    emails = extractor.extract_emails([html])
    assert "support@snitch.co.in" in emails
    assert "sales@snitch.co.in" in emails
    assert "banner@2x.png" not in emails
    assert "bootstrap-icons@1.13.1" not in emails
    assert "test@test.com" not in emails


def test_phone_extraction(extractor):
    html = """
    <html>
    <body>
      <a href="tel:+919876543210">Call Us</a>
      <p>Customer Care: +91 80 4123 4567 or 09876543210</p>
    </body>
    </html>
    """
    phones = extractor.extract_phones([html])
    assert any("+919876543210" in p for p in phones)


def test_social_extraction(extractor):
    html = """
    <html>
    <body>
      <footer>
        <a href="https://www.instagram.com/snitchonline/?hl=en">Instagram</a>
        <a href="https://facebook.com/snitchonline?utm_source=footer">Facebook</a>
        <a href="https://linkedin.com/company/snitch-apparel">LinkedIn</a>
        <a href="https://youtube.com/@snitchofficial">YouTube</a>
        <!-- Share button to be excluded -->
        <a href="https://www.facebook.com/sharer/sharer.php?u=https://snitch.co.in">Share</a>
      </footer>
    </body>
    </html>
    """
    socials = extractor.extract_socials([html])
    assert "https://instagram.com/snitchonline" in socials
    assert "https://facebook.com/snitchonline" in socials
    assert "https://linkedin.com/company/snitch-apparel" in socials
    assert "https://youtube.com/@snitchofficial" in socials
    assert not any("sharer.php" in s for s in socials)


def test_category_extraction(extractor):
    # Fashion store
    fashion_html = """
    <html>
    <head><title>Men's Casual Shirts & T-Shirts Online</title></head>
    <body>
      <nav><a href="/collections/jeans">Denim Jeans</a><a href="/collections/shirts">Oversized T-Shirts</a></nav>
      <h1>Trendy Streetwear and Clothing</h1>
    </body>
    </html>
    """
    assert extractor.extract_category(fashion_html) == "apparel & fashion"

    # Beauty store
    beauty_html = """
    <html>
    <head>
      <title>Natural Skincare & Beauty Products</title>
      <meta name="description" content="Shop Vitamin C Serum, Moisturizer and Sunscreen for glowing skin.">
    </head>
    <body>
      <h1>Clean Beauty Essentials</h1>
    </body>
    </html>
    """
    assert extractor.extract_category(beauty_html) == "beauty & skincare"


def test_tagline_description_extraction(extractor):
    html = """
    <html>
    <head>
      <meta name="description" content="India's leading handcrafted brass and copper tableware brand. Pure elegance for your home.">
      <meta property="og:description" content="Backup og description">
    </head>
    <body><h1>Copper Utensils</h1></body>
    </html>
    """
    desc = extractor.extract_tagline_description(html)
    assert "handcrafted brass and copper tableware" in desc


def test_logo_extraction_rejects_favicon(extractor):
    html = """
    <html>
    <head>
      <link rel="icon" href="/assets/favicon.ico">
      <link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
    </head>
    <body>
      <header>
        <img class="header__heading-logo brand-logo" src="//cdn.shopify.com/s/files/1/001/files/logo_black.png?v=123" alt="Brand Logo">
      </header>
    </body>
    </html>
    """
    logo_url = extractor.extract_logo("https://brand.in", html)
    assert "favicon" not in logo_url.lower()
    assert "logo_black.png" in logo_url


def test_placeholder_email_rejection(extractor):
    html = """
    <html>
    <body>
      <p>Contact: support@example.com</p>
      <p>Contact: info@domain.com</p>
      <p>Contact: user@yourdomain.com</p>
      <p>Contact: test@test.com</p>
      <p>Real Contact: help@realbrand.in</p>
    </body>
    </html>
    """
    emails = extractor.extract_emails([html])
    assert "help@realbrand.in" in emails
    assert "support@example.com" not in emails
    assert "info@domain.com" not in emails
    assert "user@yourdomain.com" not in emails
    assert "test@test.com" not in emails


def test_placeholder_logo_rejection(extractor):
    html = """
    <html>
    <body>
      <header>
        <img class="logo" src="//cdn.shopify.com/s/files/1/001/files/no-image-2048.png" alt="No image">
      </header>
    </body>
    </html>
    """
    logo_url = extractor.extract_logo("https://brand.in", html)
    assert logo_url == ""

    html_valid = """
    <html>
    <body>
      <header>
        <img class="site-header__logo" src="//cdn.shopify.com/s/files/1/001/files/actual_brand_logo.svg" alt="Brand">
      </header>
    </body>
    </html>
    """
    logo_valid = extractor.extract_logo("https://brand.in", html_valid)
    assert "actual_brand_logo.svg" in logo_valid

