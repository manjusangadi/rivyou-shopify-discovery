"""
Shopify storefront detection and scoring engine.
"""
import logging
import re
from typing import List, Tuple, Dict, Any, Optional
import dns.resolver

from src.models import ShopifyVerification

logger = logging.getLogger(__name__)


class ShopifyDetector:
    """
    Evaluates candidate websites for genuine Shopify storefront technical signals.
    Employs a weighted scoring model to eliminate false positives from blogs,
    mentions, or third-party references.
    """

    def __init__(self, threshold: int = 5):
        self.threshold = threshold

    def detect(
        self,
        domain: str,
        html_content: str,
        headers: Optional[Dict[str, str]] = None,
        check_dns: bool = False
    ) -> ShopifyVerification:
        score = 0
        signals: List[str] = []
        details: Dict[str, Any] = {}
        headers = headers or {}
        html_lower = html_content.lower() if html_content else ""

        # 1. Subdomain is *.myshopify.com (+10)
        if domain.endswith(".myshopify.com") and domain != "myshopify.com":
            score += 10
            signals.append("myshopify_subdomain")

        if html_content:
            # 2. window.Shopify presence (+5)
            if "window.shopify" in html_lower or "window['shopify']" in html_lower or 'window["shopify"]' in html_lower:
                score += 5
                signals.append("window.Shopify")

            # 3. Shopify.shop / Shopify.theme object (+5)
            if re.search(r"shopify\s*\.\s*(?:shop|theme|currency)\s*=", html_content, re.IGNORECASE):
                score += 5
                signals.append("Shopify.shop")

            # 4. Shopify CDN assets (+5)
            if "cdn.shopify.com" in html_lower:
                score += 5
                signals.append("cdn.shopify.com")

            # 5. Modern Shopify CDN asset path (/cdn/shop/) (+5)
            if "/cdn/shop/" in html_lower or "/cdn/s/files/" in html_lower:
                score += 5
                signals.append("/cdn/shop/")

            # 6. Shopify core scripts (+4)
            if any(s in html_lower for s in ["shopify_common.js", "shopify.loadfeatures", "shopify.theme"]):
                score += 4
                signals.append("shopify_core_js")

            # 7. Shopify HTML structure / sections (+2)
            if "shopify-section" in html_lower or "shopify-section-" in html_lower:
                score += 2
                signals.append("shopify-section")

            # 8. Shopify payment buttons or dynamic checkout (+2)
            if "shopify-payment-button" in html_lower or "data-shopify-button" in html_lower:
                score += 2
                signals.append("shopify-payment-button")

            # 9. Shopify custom meta tags or checkout tokens (+2)
            if 'name="shopify-checkout-api-token"' in html_lower or 'content="shopify"' in html_lower or 'data-shopify=' in html_lower:
                score += 2
                signals.append("shopify_meta_attribute")

        # 10. HTTP Headers / Cookies (+2)
        if headers:
            for h_key, h_val in headers.items():
                if "shopify" in h_key.lower() or "x-shopid" in h_key.lower() or "x-shardid" in h_key.lower():
                    score += 2
                    signals.append(f"header:{h_key.lower()}")
                    break

        # 11. DNS CNAME lookup (+2) - Only check if score is borderline or explicitly requested
        if check_dns and score < self.threshold and not domain.endswith(".myshopify.com"):
            try:
                answers = dns.resolver.resolve(domain, "CNAME", lifetime=2.0)
                for rdata in answers:
                    cname_target = str(rdata.target).lower()
                    if "myshopify.com" in cname_target or "shopify.com" in cname_target:
                        score += 2
                        signals.append("cname_to_shopify")
                        break
            except Exception:
                pass

        is_shopify = score >= self.threshold
        details = {
            "score": score,
            "signals": signals,
            "threshold": self.threshold
        }

        return ShopifyVerification(
            is_shopify=is_shopify,
            score=score,
            signals=signals,
            details=details
        )

    @staticmethod
    def verify_secondary_response(endpoint: str, data: Any) -> Tuple[bool, List[str]]:
        """
        Validates that a response from a secondary endpoint (/products.json or /cart.json)
        exhibits authentic Shopify structural signatures, not just arbitrary JSON or HTTP 200.
        """
        if not isinstance(data, dict):
            return False, []

        signals: List[str] = []
        if "products.json" in endpoint:
            if "products" in data and isinstance(data["products"], list):
                products = data["products"]
                if len(products) == 0:
                    signals.append("shopify_products_json_empty")
                    return True, signals
                sample = products[0]
                if isinstance(sample, dict):
                    shopify_product_keys = {"id", "title", "handle", "variants", "images", "vendor", "product_type"}
                    matching = shopify_product_keys.intersection(sample.keys())
                    if len(matching) >= 3:
                        signals.append("shopify_products_json_schema")
                        return True, signals

        elif "cart.json" in endpoint or "cart.js" in endpoint:
            shopify_cart_keys = {
                "token", "note", "attributes", "original_total_price",
                "total_price", "total_discount", "total_weight", "item_count",
                "items", "requires_shipping", "currency"
            }
            matching = shopify_cart_keys.intersection(data.keys())
            specific_keys = {"token", "requires_shipping", "original_total_price", "item_count"}
            if len(matching) >= 4 and any(k in data for k in specific_keys):
                signals.append("shopify_cart_json_schema")
                return True, signals

        return False, []

