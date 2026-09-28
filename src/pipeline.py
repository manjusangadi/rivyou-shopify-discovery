"""
End-to-end pipeline orchestrating discovery, verification, extraction, deduplication, and export.
"""
import asyncio
import csv
import json
import logging
from pathlib import Path
import time
from typing import List, Dict, Any, Optional, Set, Tuple
import pandas as pd

from src.config import Config, default_config
from src.fetch import AsyncFetcher, FetchResult
from src.robots import RobotsChecker
from src.discovery import CandidateDiscoveryManager
from src.shopify import ShopifyDetector
from src.india import IndiaVerifier
from src.extract import DataExtractor
from src.models import StoreRecord, AuditRecord, CandidateDomain
from src.utils import normalize_domain, canonical_url

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Orchestrates the entire Shopify India discovery and verification lifecycle.
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or default_config
        self.fetcher = AsyncFetcher(self.config)
        self.robots = RobotsChecker(user_agent=self.config.user_agent, request_timeout=self.config.request_timeout)
        self.discovery = CandidateDiscoveryManager(self.config, self.fetcher)
        self.shopify_detector = ShopifyDetector(threshold=self.config.shopify_threshold)
        self.india_verifier = IndiaVerifier(threshold=self.config.india_threshold)
        self.extractor = DataExtractor()

    async def run(
        self,
        target: Optional[int] = None,
        sources: Optional[List[str]] = None,
        seed_path: Optional[str] = None,
        max_pages: Optional[int] = None
    ) -> Dict[str, Any]:
        start_time = time.time()
        target_count = target or self.config.target
        chosen_sources = sources or ["all"]

        logger.info(f"=== Starting Pipeline Run (Target: {target_count} stores) ===")

        # ==========================================
        # Stage 1: Candidate Discovery & Deduplication
        # ==========================================
        candidates, discovery_diag = await self.discovery.discover_candidates(
            sources=chosen_sources,
            seed_path=seed_path,
            max_pages=max_pages
        )

        candidate_count = len(candidates)
        if candidate_count == 0:
            logger.error("No candidate domains discovered. Terminating pipeline early.")
            return {"status": "failed", "error": "No candidate domains discovered"}

        # ==========================================
        # Stage 2: Verification and Deep Extraction
        # ==========================================
        logger.info(f"=== Beginning Store Verification (Processing up to {candidate_count} candidates) ===")
        verified_stores: List[StoreRecord] = []
        audit_records: List[AuditRecord] = []
        processed_canonical_domains: Set[str] = set()

        shopify_verified_count = 0
        india_verified_count = 0
        processed_candidates = 0

        # Process candidates concurrently in managed batches
        batch_size = max(5, self.config.max_concurrency)

        for i in range(0, len(candidates), batch_size):
            if len(verified_stores) >= target_count:
                logger.info(f"Target count of {target_count} verified stores reached!")
                break

            batch = candidates[i : i + batch_size]
            tasks = [self._process_candidate(cand) for cand in batch]
            results = await asyncio.gather(*tasks)

            for store_rec, audit_rec in results:
                audit_records.append(audit_rec)
                processed_candidates += 1

                if audit_rec.shopify_verified:
                    shopify_verified_count += 1
                if audit_rec.india_verified:
                    india_verified_count += 1

                if store_rec:
                    # Deduplicate based on final canonical domain
                    norm_final = normalize_domain(store_rec.domain_url)
                    if norm_final not in processed_canonical_domains:
                        processed_canonical_domains.add(norm_final)
                        verified_stores.append(store_rec)
                        logger.info(
                            f"[{len(verified_stores)}/{target_count}] Verified: {norm_final} | "
                            f"Category: {store_rec.category} | State: {store_rec.state or 'N/A'}"
                        )

            # Progress log every 20 candidates
            if processed_candidates % 20 == 0:
                logger.info(
                    f"Progress: {processed_candidates}/{candidate_count} candidates scanned | "
                    f"Shopify Verified: {shopify_verified_count} | India Verified: {india_verified_count} | "
                    f"Final Stores: {len(verified_stores)}"
                )

        # ==========================================
        # Stage 3: Output Generation & Metrics
        # ==========================================
        elapsed = time.time() - start_time
        summary = self._export_results(
            verified_stores=verified_stores,
            audit_records=audit_records,
            candidate_count=candidate_count,
            unique_candidate_count=candidate_count,
            shopify_verified=shopify_verified_count,
            india_verified=india_verified_count,
            elapsed_seconds=elapsed
        )

        await self.fetcher.close()
        logger.info(f"=== Pipeline Finished in {elapsed:.2f}s ===")
        return summary

    async def _process_candidate(self, candidate: CandidateDomain) -> Tuple[Optional[StoreRecord], AuditRecord]:
        domain = candidate.domain
        audit = AuditRecord(domain_url=f"https://{domain}")

        # 1. Robots.txt check for homepage
        client = await self.fetcher.get_client()
        allowed = await self.robots.is_allowed(client, domain, "/")
        audit.robots_allowed = allowed

        if not allowed:
            audit.errors = "Robots.txt blocks homepage"
            return None, audit

        # 2. Fetch homepage
        home_url = f"https://{domain}"
        res = await self.fetcher.fetch(home_url, domain_key=domain)
        audit.http_status = res.status_code
        audit.final_url = res.final_url

        if res.status_code != 200 or not res.text:
            audit.errors = res.error or f"HTTP {res.status_code}"
            audit.final_decision = "REJECTED_FETCH_ERROR"
            audit.rejection_reason = audit.errors
            return None, audit

        # 2.5 Active storefront and Demo/Test store check
        is_active, inactive_reason = self._check_active_and_genuine_store(res, domain)
        if not is_active:
            audit.final_decision = "REJECTED_INACTIVE"
            audit.rejection_reason = inactive_reason or "Inactive or demo store"
            audit.errors = audit.rejection_reason
            return None, audit

        # 3. Shopify Verification (Primary Detection)
        shp_ver = self.shopify_detector.detect(
            domain=domain,
            html_content=res.text,
            headers=res.headers
        )

        # Borderline Shopify Secondary Verification
        # Only probed if candidate already has primary technical signals (score >= 2 and < threshold)
        if not shp_ver.is_shopify and 2 <= shp_ver.score < self.config.shopify_threshold:
            # Check products.json if robots allowed
            if await self.robots.is_allowed(client, domain, "/products.json"):
                prod_res = await self.fetcher.fetch(f"https://{domain}/products.json?limit=1", domain_key=domain)
                if prod_res.status_code == 200 and prod_res.text:
                    try:
                        data = json.loads(prod_res.text)
                        valid, sigs = self.shopify_detector.verify_secondary_response("/products.json", data)
                        if valid:
                            shp_ver.score += 2
                            shp_ver.signals.extend(sigs)
                            audit.shopify_secondary_verified = True
                    except Exception:
                        pass

            # If still below threshold, check cart.json if robots allowed
            if (shp_ver.score < self.config.shopify_threshold) and await self.robots.is_allowed(client, domain, "/cart.json"):
                cart_res = await self.fetcher.fetch(f"https://{domain}/cart.json", domain_key=domain)
                if cart_res.status_code == 200 and cart_res.text:
                    try:
                        data = json.loads(cart_res.text)
                        valid, sigs = self.shopify_detector.verify_secondary_response("/cart.json", data)
                        if valid:
                            shp_ver.score += 2
                            shp_ver.signals.extend(sigs)
                            audit.shopify_secondary_verified = True
                    except Exception:
                        pass

            shp_ver.is_shopify = (shp_ver.score >= self.config.shopify_threshold)

        audit.shopify_verified = shp_ver.is_shopify
        audit.shopify_score = shp_ver.score
        audit.shopify_signals = ";".join(shp_ver.signals)

        if not shp_ver.is_shopify:
            audit.final_decision = "REJECTED_NON_SHOPIFY"
            audit.rejection_reason = f"Shopify score {shp_ver.score} < threshold {self.config.shopify_threshold}"
            return None, audit

        # 4. India Verification (initial homepage pass)
        ind_ver = self.india_verifier.verify(
            domain=domain,
            html_content=res.text
        )
        audit.india_score = ind_ver.score
        audit.india_signals = ";".join(ind_ver.signals)
        audit.strong_india_evidence = ";".join(ind_ver.details.get("strong_location_signals", []))
        audit.state_source = ind_ver.state_source or ""

        # 5. Discover internal contact / about pages (up to 4 prioritized links)
        internal_links = self.extractor.discover_internal_links(res.final_url, res.text, max_links=4)
        audit.contact_pages_checked = len(internal_links)

        # Concurrently fetch allowed internal contact/about pages
        internal_pages_html: List[str] = [res.text]
        if internal_links:
            allowed_links = []
            for link in internal_links:
                path = "/" + link.split(domain, 1)[-1].lstrip("/")
                if await self.robots.is_allowed(client, domain, path):
                    allowed_links.append(link)

            if allowed_links:
                fetch_tasks = [self.fetcher.fetch(link, domain_key=domain) for link in allowed_links]
                page_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                for page_res in page_results:
                    if isinstance(page_res, type(res)) and page_res.status_code == 200 and page_res.text:
                        internal_pages_html.append(page_res.text)

        # Secondary India verification pass on combined text if initial score was borderline or missing state
        if len(internal_pages_html) > 1:
            combined_text = " ".join(internal_pages_html[1:])
            ind_ver_full = self.india_verifier.verify(
                domain=domain,
                html_content=res.text,
                all_pages_text=combined_text
            )
            # Take stronger results
            if ind_ver_full.score > ind_ver.score or (not ind_ver.is_india and ind_ver_full.is_india):
                ind_ver = ind_ver_full
                audit.india_score = ind_ver.score
                audit.india_signals = ";".join(ind_ver.signals)
                audit.strong_india_evidence = ";".join(ind_ver.details.get("strong_location_signals", []))
                if ind_ver.state_source:
                    audit.state_source = ind_ver.state_source

        audit.india_verified = ind_ver.is_india

        if not ind_ver.is_india:
            audit.final_decision = "REJECTED_NON_INDIA"
            audit.rejection_reason = (
                f"India score {ind_ver.score} < threshold {self.config.india_threshold}"
                if ind_ver.score < self.config.india_threshold
                else "Lacks strong Indian business location evidence"
            )
            return None, audit

        # ==========================================
        # 6. Deep Attribute Extraction
        # ==========================================
        # Emails
        emails = self.extractor.extract_emails(internal_pages_html)
        audit.emails_found = len(emails)

        # Phones
        phones = self.extractor.extract_phones(internal_pages_html)
        audit.phones_found = len(phones)

        # Combined Contacts field
        all_contacts_list = []
        if emails:
            all_contacts_list.extend(emails)
        if phones:
            all_contacts_list.extend(phones)
        all_contacts_str = ";".join(all_contacts_list)

        # Socials
        socials = self.extractor.extract_socials(internal_pages_html)
        audit.socials_found = len(socials)
        socials_str = ";".join(socials)

        # Category
        category = self.extractor.extract_category(res.text)
        audit.category_source = "keyword_heuristics"

        # Tagline / Description
        tagline = self.extractor.extract_tagline_description(res.text)
        audit.description_source = "metadata_or_headings"

        # Logo URL
        logo_url = self.extractor.extract_logo(res.final_url, res.text)
        audit.logo_source = "jsonld_or_dom_img"

        # Canonical final domain URL
        final_domain_url = canonical_url(res.final_url or domain)

        audit.final_decision = "ACCEPTED"
        audit.rejection_reason = ""

        store_record = StoreRecord(
            domain_url=final_domain_url,
            all_contacts=all_contacts_str,
            socials=socials_str,
            category=category,
            tagline_description=tagline,
            logo=logo_url,
            state=ind_ver.state or ""
        )

        return store_record, audit

    def _check_active_and_genuine_store(self, res: FetchResult, domain: str) -> Tuple[bool, Optional[str]]:
        """
        Inspects storefront for active commercial status, excluding password pages,
        404/410 errors, parked domains, and obvious demo/boilerplate instances.
        """
        text_lower = res.text.lower() if res.text else ""
        url_lower = res.final_url.lower()

        # Inactive HTTP codes
        if res.status_code in {404, 410}:
            return False, f"HTTP {res.status_code} inactive"

        # Password / Opening soon pages
        if "/password" in url_lower:
            return False, "Redirects to /password"

        if "template-password" in text_lower or ('id="login_form"' in text_lower and "/password" in text_lower):
            return False, "Password-protected storefront"

        if "opening soon" in text_lower[:2500] and ("password" in text_lower[:2500] or "store will be opening soon" in text_lower):
            return False, "Opening Soon password page"

        # Parked / sale pages
        if any(p in text_lower for p in ["this domain is parked", "buy this domain", "domain for sale", "hugedomains.com"]):
            return False, "Parked or for-sale domain"

        # Demo / test storefront detection (requires corroborating evidence)
        dom_lower = domain.lower()
        demo_name_indicators = ["shopifytest", "test-shop", "teststore", "dev-shop", "demo-store", "my-test-"]
        has_demo_name = any(ind in dom_lower for ind in demo_name_indicators)

        boilerplate_phrases = [
            "write a few sentences to tell people about your store",
            "spread the word about your shop",
            "give customers details about the banner image",
            "use this text to share information about your brand"
        ]
        has_boilerplate = any(b in text_lower for b in boilerplate_phrases)

        if has_demo_name and has_boilerplate:
            return False, "Demo/test store (naming + default Shopify boilerplate copy)"

        if has_boilerplate and ("myshopify.com" in dom_lower or "test" in dom_lower):
            return False, "Default Shopify theme boilerplate with no commercial brand content"

        return True, None

    def _export_results(
        self,
        verified_stores: List[StoreRecord],
        audit_records: List[AuditRecord],
        candidate_count: int,
        unique_candidate_count: int,
        shopify_verified: int,
        india_verified: int,
        elapsed_seconds: float
    ) -> Dict[str, Any]:
        """
        Exports data/output/stores.csv, data/output/audit.csv, and data/output/summary.json.
        """
        out_dir = self.config.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1. Export stores.csv
        stores_file = self.config.stores_csv
        with open(stores_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["domain_url", "all_contacts", "socials", "category", "tagline_description", "logo", "state"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for s in verified_stores:
                writer.writerow(s.to_csv_dict())

        # 2. Export audit.csv
        audit_file = self.config.audit_csv
        with open(audit_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = [
                "domain_url", "final_url", "http_status", "shopify_verified",
                "shopify_score", "shopify_signals", "shopify_secondary_verified",
                "india_verified", "india_score", "india_signals", "strong_india_evidence",
                "state_source", "final_decision", "rejection_reason",
                "contact_pages_checked", "emails_found", "phones_found",
                "socials_found", "logo_source", "category_source",
                "description_source", "robots_allowed", "errors"
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for a in audit_records:
                writer.writerow(a.to_csv_dict())

        # 3. Calculate accurate summary metrics
        final_count = len(verified_stores)
        email_cov = sum(1 for s in verified_stores if any("@" in c for c in s.all_contacts.split(";"))) / max(1, final_count) if final_count else 0.0
        phone_cov = sum(1 for s in verified_stores if any("+" in c or c.isdigit() for c in s.all_contacts.split(";"))) / max(1, final_count) if final_count else 0.0
        social_cov = sum(1 for s in verified_stores if s.socials) / max(1, final_count) if final_count else 0.0
        state_cov = sum(1 for s in verified_stores if s.state) / max(1, final_count) if final_count else 0.0
        logo_cov = sum(1 for s in verified_stores if s.logo) / max(1, final_count) if final_count else 0.0

        summary = {
            "candidate_count": candidate_count,
            "unique_candidate_count": unique_candidate_count,
            "shopify_verified": shopify_verified,
            "india_verified": india_verified,
            "final_stores": final_count,
            "duplicates_removed": candidate_count - unique_candidate_count,
            "email_coverage": round(email_cov, 4),
            "phone_coverage": round(phone_cov, 4),
            "social_coverage": round(social_cov, 4),
            "state_coverage": round(state_cov, 4),
            "logo_coverage": round(logo_cov, 4),
            "elapsed_seconds": round(elapsed_seconds, 2)
        }

        # 4. Export summary.json
        summary_file = self.config.summary_json
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        print("\n" + "="*50)
        print(" Final Pipeline Execution Summary")
        print("="*50)
        print(f" Candidates Discovered:   {candidate_count}")
        print(f" Shopify Verified:        {shopify_verified}")
        print(f" India Verified:          {india_verified}")
        print(f" Final Stores Saved:      {final_count}")
        print(f" Email Coverage:          {email_cov*100:.1f}%")
        print(f" Phone Coverage:          {phone_cov*100:.1f}%")
        print(f" Social Coverage:         {social_cov*100:.1f}%")
        print(f" State Coverage:          {state_cov*100:.1f}%")
        print(f" Logo Coverage:           {logo_cov*100:.1f}%")
        print(f" Total Runtime:           {elapsed_seconds:.2f}s")
        print(f" Stores CSV:              {stores_file}")
        print(f" Audit CSV:               {audit_file}")
        print(f" Summary JSON:            {summary_file}")
        print("="*50 + "\n")

        return summary
