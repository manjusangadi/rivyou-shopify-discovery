"""
Data models for the Shopify India Discovery Pipeline.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class CandidateDomain:
    domain: str
    raw_url: str
    source: str


@dataclass
class ShopifyVerification:
    is_shopify: bool
    score: int
    signals: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IndiaVerification:
    is_india: bool
    score: int
    signals: List[str] = field(default_factory=list)
    state: Optional[str] = None
    state_source: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StoreRecord:
    """
    Final verified store record matching the required CSV schema:
    domain_url, all_contacts, socials, category, tagline_description, logo, state
    """
    domain_url: str
    all_contacts: str = ""
    socials: str = ""
    category: str = "other"
    tagline_description: str = ""
    logo: str = ""
    state: str = ""

    def to_csv_dict(self) -> Dict[str, str]:
        return {
            "domain_url": self.domain_url,
            "all_contacts": self.all_contacts,
            "socials": self.socials,
            "category": self.category,
            "tagline_description": self.tagline_description,
            "logo": self.logo,
            "state": self.state,
        }


@dataclass
class AuditRecord:
    """
    Audit record tracking the verification journey, signals, and sources.
    """
    domain_url: str
    final_url: str = ""
    http_status: int = 0
    shopify_verified: bool = False
    shopify_score: int = 0
    shopify_signals: str = ""
    india_verified: bool = False
    india_score: int = 0
    india_signals: str = ""
    state_source: str = ""
    contact_pages_checked: int = 0
    emails_found: int = 0
    phones_found: int = 0
    socials_found: int = 0
    logo_source: str = ""
    category_source: str = ""
    description_source: str = ""
    robots_allowed: bool = True
    errors: str = ""

    def to_csv_dict(self) -> Dict[str, Any]:
        return {
            "domain_url": self.domain_url,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "shopify_verified": self.shopify_verified,
            "shopify_score": self.shopify_score,
            "shopify_signals": self.shopify_signals,
            "india_verified": self.india_verified,
            "india_score": self.india_score,
            "india_signals": self.india_signals,
            "state_source": self.state_source,
            "contact_pages_checked": self.contact_pages_checked,
            "emails_found": self.emails_found,
            "phones_found": self.phones_found,
            "socials_found": self.socials_found,
            "logo_source": self.logo_source,
            "category_source": self.category_source,
            "description_source": self.description_source,
            "robots_allowed": self.robots_allowed,
            "errors": self.errors,
        }
