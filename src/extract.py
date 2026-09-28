"""
Information extraction engine: emails, phones, socials, category, tagline/description, and logo.
"""
import json
import logging
import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import phonenumbers

from src.utils import is_valid_email, clean_text, normalize_social_url

logger = logging.getLogger(__name__)

# Pre-defined keyword taxonomy for store categories
CATEGORY_KEYWORDS = {
    "apparel & fashion": [
        "clothing", "apparel", "saree", "kurta", "lehenga", "shirt", "t-shirt",
        "trousers", "dress", "ethnic wear", "menswear", "womenswear", "denim",
        "fashion", "hoodie", "jeans", "activewear", "streetwear", "suits"
    ],
    "beauty & skincare": [
        "skincare", "serum", "moisturizer", "sunscreen", "cleanser", "beauty",
        "cosmetics", "shampoo", "haircare", "lipstick", "perfume", "fragrance",
        "lotion", "glow", "facewash", "bodywash", "anti-aging"
    ],
    "jewelry": [
        "jewelry", "jewellery", "necklace", "earrings", "ring", "bracelet",
        "bangles", "gold", "silver", "diamond", "pendant", "choker", "anklet"
    ],
    "home decor": [
        "home decor", "decor", "cushions", "bedsheet", "curtains", "vase",
        "wall art", "rugs", "candles", "clock", "linens", "handicrafts",
        "copper", "brass", "tableware", "planters", "lamps", "lighting"
    ],
    "food & beverages": [
        "tea", "coffee", "snacks", "spices", "chocolates", "honey", "organic food",
        "dry fruits", "cookies", "beverages", "sweets", "bakery", "gourmet",
        "ayurvedic food", "healthy snacks", "brews", "oats"
    ],
    "electronics": [
        "electronics", "headphones", "earbuds", "smartwatch", "gadgets",
        "chargers", "cables", "bluetooth", "speakers", "mobile accessories",
        "powerbank", "audio"
    ],
    "sports & fitness": [
        "fitness", "gym", "workout", "protein", "supplement", "yoga",
        "activewear", "sports gear", "equipment", "dumbbell", "whey"
    ],
    "pets": [
        "pet food", "dog", "cat", "puppy", "kitten", "pet accessories",
        "dog food", "pet care", "leash", "collar", "pet toys"
    ],
    "baby & kids": [
        "baby", "kids", "toys", "toddler", "diaper", "baby clothing",
        "stroller", "nursery", "maternity", "baby care", "puzzles"
    ],
    "books & stationery": [
        "books", "stationery", "notebook", "planner", "journal", "pens",
        "stickers", "art supplies", "novel", "desk accessories"
    ],
    "kitchen": [
        "kitchenware", "cookware", "utensils", "pans", "pots", "knives",
        "cutlery", "dinnerware", "crockery", "bottles", "lunch box"
    ],
    "health & wellness": [
        "health", "wellness", "ayurveda", "vitamins", "herbal", "supplements",
        "immunity", "pain relief", "sanitary", "personal care"
    ],
    "accessories": [
        "bags", "wallets", "backpack", "belts", "sunglasses", "eyewear",
        "watch", "caps", "travel gear", "luggage", "handbags"
    ],
    "footwear": [
        "shoes", "sneakers", "sandals", "slippers", "boots", "loafers",
        "footwear", "flats", "heels", "slides"
    ],
    "furniture": [
        "furniture", "sofa", "bed", "chair", "table", "dining table",
        "wardrobe", "desk", "bookshelf", "mattress"
    ]
}


def _get_attr_str(tag, attr: str) -> str:
    val = tag.get(attr, "")
    if isinstance(val, list):
        return " ".join(str(v) for v in val).strip()
    return str(val or "").strip()


class DataExtractor:
    """
    Extracts structured store attributes:
    emails, phone numbers, social media links, categories, taglines, and logo URLs.
    """

    def discover_internal_links(self, base_url: str, html: str, max_links: int = 4) -> List[str]:
        """
        Discovers key contact/about/policies internal pages from links on the homepage,
        strictly prioritized by importance:
        1. Contact (/contact, /contact-us, /pages/contact)
        2. About (/about, /about-us, /pages/about)
        3. Support/Help (/support, /help, /customer-care)
        4. Policies/Terms/Shipping (/policies, /terms, /privacy, /shipping)
        """
        if not html:
            return []

        priority_tiers = [
            # Tier 1: Direct Contact
            ["contact-us", "contact_us", "contactus", "/contact", "pages/contact"],
            # Tier 2: About Company / Registered Info
            ["about-us", "about_us", "aboutus", "/about", "pages/about"],
            # Tier 3: Support / Help / Customer Care
            ["customer-care", "customer-service", "support", "help"],
            # Tier 4: Policies / Terms / Shipping / Returns (Often contains GSTIN, legal registered office)
            ["terms-of-service", "terms-and-conditions", "policies", "privacy-policy", "shipping-policy", "refund-policy", "terms", "shipping", "policy", "return", "refund", "faq"]
        ]

        found_by_tier: Dict[int, List[str]] = {i: [] for i in range(len(priority_tiers))}
        seen_targets: Set[str] = set()

        try:
            soup = BeautifulSoup(html, "lxml")
            parsed_base = urlparse(base_url)
            base_domain = parsed_base.netloc.lower()

            for a in soup.find_all("a", href=True):
                href = _get_attr_str(a, "href")
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue

                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)

                # Ensure link belongs to the same domain
                if parsed.netloc.lower() != base_domain:
                    continue

                clean_path = parsed.path.rstrip("/")
                if not clean_path:
                    continue

                clean_target = f"{parsed.scheme}://{parsed.netloc}{clean_path}"
                if clean_target in seen_targets:
                    continue

                path_lower = clean_path.lower()
                for tier_idx, keywords in enumerate(priority_tiers):
                    if any(kw in path_lower for kw in keywords):
                        found_by_tier[tier_idx].append(clean_target)
                        seen_targets.add(clean_target)
                        break

        except Exception as e:
            logger.debug(f"[extract] Error discovering internal links for {base_url}: {e}")

        # Flatten in prioritized order up to max_links
        ordered_links: List[str] = []
        for tier_idx in range(len(priority_tiers)):
            for link in found_by_tier[tier_idx]:
                if len(ordered_links) < max_links:
                    ordered_links.append(link)
                else:
                    break
            if len(ordered_links) >= max_links:
                break

        return ordered_links

    def extract_emails(self, html_contents: List[str]) -> List[str]:
        """
        Extracts verified business email addresses from HTML contents (mailto links, text regex, JSON-LD).
        """
        found_emails: Set[str] = set()

        for html in html_contents:
            if not html:
                continue

            try:
                soup = BeautifulSoup(html, "lxml")

                # 1. mailto: links
                for a in soup.find_all("a", href=True):
                    href = _get_attr_str(a, "href")
                    if href.lower().startswith("mailto:"):
                        email_candidate = href.split(":", 1)[1].split("?")[0].strip()
                        if is_valid_email(email_candidate):
                            found_emails.add(email_candidate.lower())

                # 2. Text regex
                text = soup.get_text(separator=" ")
                matches = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
                for candidate in matches:
                    cand = candidate.strip().strip(".,;:()")
                    if is_valid_email(cand):
                        found_emails.add(cand.lower())

            except Exception as e:
                logger.debug(f"[extract] Error parsing emails: {e}")

        # Return sorted list of deduplicated emails
        return sorted(list(found_emails))

    def extract_phones(self, html_contents: List[str]) -> List[str]:
        """
        Extracts verified phone numbers using the phonenumbers package,
        prioritizing Indian numbers in E.164 format (+91...).
        """
        found_phones: Set[str] = set()

        for html in html_contents:
            if not html:
                continue

            try:
                soup = BeautifulSoup(html, "lxml")

                # 1. tel: links
                for a in soup.find_all("a", href=True):
                    href = _get_attr_str(a, "href")
                    if href.lower().startswith("tel:"):
                        cand = href.split(":", 1)[1].split("?")[0].strip()
                        self._parse_and_add_phone(cand, found_phones)

                # 2. Plain text extraction via phonenumbers PhoneNumberMatcher
                text = soup.get_text(separator=" ")
                for match in phonenumbers.PhoneNumberMatcher(text, "IN"):
                    num = match.number
                    if phonenumbers.is_valid_number(num) or phonenumbers.is_possible_number(num):
                        formatted = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
                        found_phones.add(formatted)

            except Exception as e:
                logger.debug(f"[extract] Error parsing phone numbers: {e}")

        return sorted(list(found_phones))

    def _parse_and_add_phone(self, raw_phone: str, phone_set: Set[str]):
        """Parses a candidate phone string with phonenumbers."""
        if not raw_phone:
            return
        # Remove common phone junk
        cleaned = re.sub(r"[^\d+]", "", raw_phone)
        if len(cleaned) < 8:
            return

        try:
            parsed = phonenumbers.parse(cleaned, "IN")
            if phonenumbers.is_valid_number(parsed) or phonenumbers.is_possible_number(parsed):
                formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                phone_set.add(formatted)
        except Exception:
            pass

    def extract_socials(self, html_contents: List[str]) -> List[str]:
        """
        Extracts official brand social media URLs from page links.
        """
        found_socials: Set[str] = set()

        for html in html_contents:
            if not html:
                continue

            try:
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    href = _get_attr_str(a, "href")
                    norm_social = normalize_social_url(href)
                    if norm_social:
                        found_socials.add(norm_social)
            except Exception as e:
                logger.debug(f"[extract] Error extracting socials: {e}")

        return sorted(list(found_socials))

    def extract_category(self, homepage_html: str) -> str:
        """
        Infers the store category from title, meta description, headings,
        navigation, and product/collection links using keyword scoring.
        """
        if not homepage_html:
            return "other"

        try:
            soup = BeautifulSoup(homepage_html, "lxml")
            title = soup.title.get_text() if soup.title else ""
            meta_desc = ""
            desc_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
            if desc_tag:
                meta_desc = _get_attr_str(desc_tag, "content")

            headings = " ".join([h.get_text() for h in soup.find_all(["h1", "h2"])])
            nav_links = " ".join([a.get_text() for a in soup.find_all("nav")])

            combined_text = f"{title} {meta_desc} {headings} {nav_links}".lower()

            scores: Dict[str, int] = {cat: 0 for cat in CATEGORY_KEYWORDS}

            for cat, keywords in CATEGORY_KEYWORDS.items():
                for kw in keywords:
                    # Give higher weight to matches in title and meta description
                    if kw in title.lower():
                        scores[cat] += 4
                    if kw in meta_desc.lower():
                        scores[cat] += 3
                    if re.search(rf"\b{re.escape(kw)}\b", combined_text):
                        scores[cat] += 1

            best_category, highest_score = max(scores.items(), key=lambda item: item[1])
            if highest_score >= 2:
                return best_category
            return "other"

        except Exception as e:
            logger.debug(f"[extract] Error determining category: {e}")
            return "other"

    def extract_tagline_description(self, homepage_html: str) -> str:
        """
        Extracts original store description without hallucinating or rewriting:
        Priority:
        1. meta description
        2. og:description
        3. JSON-LD description
        4. homepage hero text / H1
        """
        if not homepage_html:
            return ""

        try:
            soup = BeautifulSoup(homepage_html, "lxml")

            # 1. Meta description
            meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
            if meta_desc:
                content_val = _get_attr_str(meta_desc, "content")
                if content_val:
                    cleaned = clean_text(content_val)
                    if len(cleaned) > 20:
                        return cleaned

            # 2. og:description
            og_desc = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "og:description"})
            if og_desc:
                content_val = _get_attr_str(og_desc, "content")
                if content_val:
                    cleaned = clean_text(content_val)
                    if len(cleaned) > 20:
                        return cleaned

            # 3. JSON-LD description
            for script in soup.find_all("script", type="application/ld+json"):
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string.strip())
                    items = data if isinstance(data, list) else [data]
                    for it in items:
                        if isinstance(it, dict) and it.get("description"):
                            cleaned = clean_text(it["description"])
                            if len(cleaned) > 20:
                                return cleaned
                except Exception:
                    continue

            # 4. First H1 heading
            h1 = soup.find("h1")
            if h1 and h1.get_text():
                cleaned = clean_text(h1.get_text())
                if len(cleaned) > 10:
                    return cleaned

        except Exception as e:
            logger.debug(f"[extract] Error extracting tagline/description: {e}")

        return ""

    def extract_logo(self, base_url: str, homepage_html: str) -> str:
        """
        Extracts actual brand logo URL (NOT favicon).
        Rejects favicon.ico, favicon.png, apple-touch-icon, payment icons, avatars.
        Priority:
        1. JSON-LD Organization logo
        2. <img> tag matching logo classes/alt/src
        3. Shopify theme header logo
        """
        if not homepage_html:
            return ""

        try:
            soup = BeautifulSoup(homepage_html, "lxml")

            # Priority 1: JSON-LD Organization logo
            for script in soup.find_all("script", type="application/ld+json"):
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string.strip())
                    items = data if isinstance(data, list) else [data]
                    for it in items:
                        if isinstance(it, dict):
                            logo_cand = it.get("logo")
                            if isinstance(logo_cand, dict):
                                logo_cand = logo_cand.get("url")
                            if logo_cand and isinstance(logo_cand, str):
                                full_logo = urljoin(base_url, logo_cand.strip())
                                if self._is_valid_logo_url(full_logo):
                                    return full_logo
                except Exception:
                    continue

            # Priority 2: <img> with alt or class matching brand logo
            for img in soup.find_all("img"):
                src = _get_attr_str(img, "src") or _get_attr_str(img, "data-src") or _get_attr_str(img, "srcset")
                if not src:
                    continue

                # If srcset, take first image URL
                if " " in src and "," in src:
                    src = src.split(",")[0].strip().split(" ")[0]

                alt = _get_attr_str(img, "alt").lower()
                cls = _get_attr_str(img, "class").lower()
                img_id = _get_attr_str(img, "id").lower()
                src_lower = src.lower()

                # Score logo signals
                is_logo_cand = False
                if "logo" in alt or "logo" in cls or "logo" in img_id or "logo" in src_lower:
                    is_logo_cand = True
                elif "brand" in alt or "brand" in cls or "header__heading-logo" in cls:
                    is_logo_cand = True

                if is_logo_cand:
                    full_url = urljoin(base_url, src.strip())
                    if self._is_valid_logo_url(full_url):
                        return full_url

        except Exception as e:
            logger.debug(f"[extract] Error extracting logo: {e}")

        return ""

    def _is_valid_logo_url(self, url: str) -> bool:
        """Ensures the logo URL is valid and is NOT a favicon, icon, or payment badge."""
        if not url or not url.startswith(("http://", "https://")):
            return False

        url_lower = url.lower()

        # Reject favicons, UI icons, badges, and obvious placeholders
        if any(bad in url_lower for bad in [
            "favicon", "apple-touch-icon", "mask-icon", "browserconfig",
            "avatar", "payment", "visa", "mastercard", "paypal", "badge",
            "star.svg", "rating", "cart", "search", "loading", "spinner",
            "no-image", "no_image", "no-image-2048", "placeholder",
            "default-image", "default_image", "product-placeholder", "blank.png"
        ]):
            return False

        # Must have valid image extension or cdn path
        if not any(ext in url_lower for ext in [".png", ".jpg", ".jpeg", ".webp", ".svg", "/files/", "/cdn/"]):
            return False

        return True
