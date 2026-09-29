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


def test_secondary_verification_products_json_valid():
    valid_data = {
        "products": [
            {
                "id": 123456789,
                "title": "Classic Cotton T-Shirt",
                "handle": "classic-cotton-t-shirt",
                "vendor": "BrandIndia",
                "variants": [{"id": 987654321, "price": "999.00"}],
                "images": []
            }
        ]
    }
    is_valid, signals = ShopifyDetector.verify_secondary_response("/products.json", valid_data)
    assert is_valid is True
    assert "shopify_products_json_schema" in signals


def test_secondary_verification_products_json_invalid():
    # Non-dict data
    assert ShopifyDetector.verify_secondary_response("/products.json", "<html>Not JSON</html>")[0] is False
    # Generic dict without products array
    assert ShopifyDetector.verify_secondary_response("/products.json", {"status": "ok", "items": []})[0] is False
    # Dict with products array but lacking Shopify-specific product keys
    assert ShopifyDetector.verify_secondary_response("/products.json", {"products": [{"sku": "123", "foo": "bar"}]})[0] is False


def test_secondary_verification_cart_json_valid():
    valid_cart = {
        "token": "c1-abcdef123456",
        "note": None,
        "attributes": {},
        "original_total_price": 0,
        "total_price": 0,
        "total_discount": 0,
        "total_weight": 0,
        "item_count": 0,
        "items": [],
        "requires_shipping": False,
        "currency": "INR"
    }
    is_valid, signals = ShopifyDetector.verify_secondary_response("/cart.json", valid_cart)
    assert is_valid is True
    assert "shopify_cart_json_schema" in signals


def test_secondary_verification_cart_json_generic_rejected():
    # Single generic key "token" must NOT be treated as sufficient evidence
    generic_token = {"token": "xyz123"}
    is_valid, _ = ShopifyDetector.verify_secondary_response("/cart.json", generic_token)
    assert is_valid is False

    # Generic shopping cart schema from other e-commerce engines
    other_cart = {"cart_id": "999", "total": 500, "status": "active"}
    is_valid, _ = ShopifyDetector.verify_secondary_response("/cart.json", other_cart)
    assert is_valid is False


def test_secondary_verification_supporting_weight_does_not_override_zero_signal_store(detector):
    # Secondary check is +2 supporting points and requires primary score >= 2 to be applied.
    # A store with 0 primary signals cannot be verified by secondary alone.
    html = "<html><body>Plain non-Shopify website</body></html>"
    ver = detector.detect(domain="plainnonshopify.com", html_content=html)
    assert ver.score == 0
    assert ver.is_shopify is False

