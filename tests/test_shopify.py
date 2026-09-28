"""
Unit tests for Shopify detection logic, technical signal scoring, and false positive prevention.
"""
import pytest
from src.shopify import ShopifyDetector


@pytest.fixture
def detector():
    return ShopifyDetector(threshold=5)


def test_myshopify_subdomain_positive(detector):
    ver = detector.detect(
        domain="sugar-cosmetics.myshopify.com",
        html_content="<html><head><title>Sugar</title></head><body></body></html>"
    )
    assert ver.is_shopify is True
    assert ver.score >= 10
    assert "myshopify_subdomain" in ver.signals


def test_window_shopify_and_cdn_signals(detector):
    html = """
    <!DOCTYPE html>
    <html>
    <head>
      <script>
        window.Shopify = window.Shopify || {};
        Shopify.shop = "brand.myshopify.com";
      </script>
      <link rel="stylesheet" href="https://cdn.shopify.com/s/files/1/001/style.css">
    </head>
    <body>
      <div id="shopify-section-header" class="shopify-section">Header</div>
    </body>
    </html>
    """
    ver = detector.detect(domain="mycustombrand.in", html_content=html)
    assert ver.is_shopify is True
    assert ver.score >= 15
    assert "window.Shopify" in ver.signals
    assert "Shopify.shop" in ver.signals
    assert "cdn.shopify.com" in ver.signals
    assert "shopify-section" in ver.signals


def test_modern_cdn_shop_path(detector):
    html = """
    <html>
    <head>
      <script src="//brand.com/cdn/shop/t/1/assets/app.js"></script>
    </head>
    <body>
      <button class="shopify-payment-button">Buy Now</button>
    </body>
    </html>
    """
    ver = detector.detect(domain="brand.in", html_content=html)
    assert ver.is_shopify is True
    assert ver.score >= 7
    assert "/cdn/shop/" in ver.signals
    assert "shopify-payment-button" in ver.signals


def test_false_positive_blog_mention_rejected(detector):
    # Website with blog text "Shopify" but NO technical storefront signals
    html = """
    <!DOCTYPE html>
    <html>
    <head>
      <title>E-commerce Tech Blog</title>
      <meta name="description" content="Why we decided to migrate our store away from Shopify to custom Django backend.">
    </head>
    <body>
      <h1>Migrating From Shopify</h1>
      <p>Shopify was great for our early days, but as an enterprise we needed custom logic.</p>
    </body>
    </html>
    """
    ver = detector.detect(domain="techblog.com", html_content=html)
    # Must NOT pass Shopify detection
    assert ver.is_shopify is False
    assert ver.score < 5
    assert len(ver.signals) == 0


def test_headers_detection(detector):
    html = "<html><body>Minimal HTML</body></html>"
    headers = {"x-shopid": "12345678", "server": "cloudflare"}
    ver = detector.detect(domain="brand.com", html_content=html, headers=headers)
    assert "header:x-shopid" in ver.signals
    assert ver.score == 2  # Alone not enough to pass threshold of 5
    assert ver.is_shopify is False
