"""
Utility functions for domain normalization, validation, cleaning, and formatting.
"""
import html
import re
from typing import Optional, Set
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


# Blacklisted domains that should never be treated as candidate Shopify stores
DOMAIN_BLACKLIST = {
    "shopify.com",
    "myshopify.com",
    "cdn.shopify.com",
    "apps.shopify.com",
    "themes.shopify.com",
    "help.shopify.com",
    "community.shopify.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "youtube.com",
    "pinterest.com",
    "google.com",
    "github.com",
    "apple.com",
    "play.google.com",
    "apps.apple.com",
    "wikipedia.org",
    "t.co",
    "bit.ly",
    "tinyurl.com",
    "onshopify.com",
    "prestasites.com",
    "themetix.com",
    "pluginu.com",
    "envato.com",
    "themeforest.net",
}

# Image / asset extensions to reject if regex matches filename as email
INVALID_EMAIL_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".ico",
    ".js", ".css", ".woff", ".woff2", ".ttf", ".eot", ".json", ".xml"
}

# Generic / placeholder emails to discard
PLACEHOLDER_EMAILS = {
    "example@example.com",
    "test@test.com",
    "info@example.com",
    "user@example.com",
    "email@domain.com",
    "yourname@email.com",
    "support@yourdomain.com",
}


def normalize_domain(url_or_domain: str) -> str:
    """
    Normalizes a URL or domain string:
    - Strips http://, https://, whitespace
    - Strips www. prefix
    - Strips port, path, query strings, fragments, trailing slashes
    - Lowercases
    - PRESERVES subdomains (e.g., brand1.myshopify.com is NOT collapsed to myshopify.com)
    """
    if not url_or_domain:
        return ""

    val = url_or_domain.strip().lower()

    # Prepend http:// if no scheme for urlparse to parse netloc properly
    if not val.startswith(("http://", "https://")):
        val = "http://" + val

    try:
        parsed = urlparse(val)
        host = parsed.netloc or parsed.path.split("/")[0]
        # Remove port if present
        host = host.split(":")[0].strip()
        # Remove www. prefix
        if host.startswith("www."):
            host = host[4:]
        # Remove trailing dots or slashes
        host = host.strip("./")
        return host
    except Exception:
        # Fallback regex strip
        val = re.sub(r"^https?://", "", val)
        val = re.sub(r"^www\.", "", val)
        val = val.split("/")[0].split("?")[0].split("#")[0].split(":")[0].strip("./")
        return val


def is_valid_domain(domain: str) -> bool:
    """
    Verifies that a normalized domain is well-formed, not blacklisted,
    and represents an actual candidate website.
    """
    if not domain or len(domain) < 4 or len(domain) > 255:
        return False

    if domain in DOMAIN_BLACKLIST:
        return False

    # Check for invalid characters
    if not re.match(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$", domain):
        return False

    # Must contain at least one dot
    parts = domain.split(".")
    if len(parts) < 2:
        return False

    # Top-level domain must not be purely numeric
    if parts[-1].isdigit():
        return False

    # Do not treat raw myshopify.com as candidate (store subdomains are allowed)
    if domain == "myshopify.com":
        return False

    return True


def canonical_url(domain: str) -> str:
    """Formats a normalized domain into a canonical HTTPS URL."""
    norm = normalize_domain(domain)
    return f"https://{norm}" if norm else ""


def clean_text(text: Optional[str], max_length: int = 500) -> str:
    """
    Cleans raw text: unescapes HTML entities, strips extra whitespaces/newlines,
    and truncates to max_length without cutting words awkwardly.
    """
    if not text:
        return ""

    cleaned = html.unescape(text)
    # Remove HTML tags if any residual tags are left
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Normalize whitespaces and newlines
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) > max_length:
        truncated = cleaned[:max_length].rsplit(" ", 1)[0]
        return truncated + "..." if truncated else cleaned[:max_length]
    return cleaned


def is_valid_email(email: str) -> bool:
    """
    Validates email syntax and filters out static asset names,
    version package tags, and dummy emails.
    """
    if not email or len(email) < 6 or len(email) > 120:
        return False

    email = email.strip().lower()

    if email in PLACEHOLDER_EMAILS:
        return False

    # Must match standard email pattern
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", email):
        return False

    # Check against invalid extensions
    for ext in INVALID_EMAIL_EXTENSIONS:
        if email.endswith(ext):
            return False

    # Check for package version patterns like bootstrap-icons@1.13.1
    domain_part = email.split("@")[-1]
    if re.match(r"^[0-9.]+$", domain_part):
        return False

    # Ensure TLD has at least 2 alpha characters
    tld = domain_part.split(".")[-1]
    if not tld.isalpha() or len(tld) < 2:
        return False

    return True


def normalize_social_url(url: str) -> Optional[str]:
    """
    Normalizes social media links:
    - Cleans tracking query parameters (?utm_*, ?ref=, ?fbclid=, etc.)
    - Rejects share dialogs, widgets, and main platform root pages
    - Lowercases scheme and domain, preserves handle
    """
    if not url:
        return None

    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        # Validate social domains
        valid_platforms = (
            "instagram.com", "facebook.com", "twitter.com", "x.com",
            "linkedin.com", "youtube.com", "pinterest.com"
        )
        matched = False
        for p in valid_platforms:
            if domain == p or domain.endswith("." + p):
                matched = True
                break

        if not matched:
            return None

        # Filter out share dialogs and intent URLs
        path = parsed.path.rstrip("/")
        path_lower = path.lower()

        # Share endpoints
        if any(bad in path_lower for bad in [
            "sharer", "share.php", "/share", "intent/tweet", "sharearticle",
            "pin/create", "dialog/share", "widgets", "plugins", "/business",
            "/help", "/policy", "/policies"
        ]):
            return None

        # Reject pure homepage without profile handle
        if path == "" or path == "/":
            return None

        # Reject common generic paths
        if path_lower in [
            "/home", "/login", "/signup", "/explore", "/privacy",
            "/terms", "/about", "/help", "/hashtag", "/search", "/share"
        ]:
            return None

        # Clean query parameters: strip tracking params
        query_dict = parse_qs(parsed.query)
        cleaned_queries = {
            k: v for k, v in query_dict.items()
            if not k.startswith("utm_") and k not in {"fbclid", "ref", "igshid", "locale", "hl"}
        }
        new_query = urlencode(cleaned_queries, doseq=True) if cleaned_queries else ""

        normalized = urlunparse((
            "https",
            domain,
            path,
            "",
            new_query,
            ""
        ))
        return normalized

    except Exception:
        return None
