"""
Multi-source candidate discovery engine: OnShopify directory, Common Crawl, and local seeds.
"""
import asyncio
import logging
import re
from typing import List, Set, Dict, Optional, Tuple, Any
from bs4 import BeautifulSoup
import httpx

from src.config import Config
from src.fetch import AsyncFetcher
from src.models import CandidateDomain
from src.utils import normalize_domain, is_valid_domain

logger = logging.getLogger(__name__)


class OnShopifyDiscovery:
    """
    Crawls public OnShopify India directory with pagination support.
    Extracts candidate store domains from directory pages and detail cards.
    """

    def __init__(self, config: Config, fetcher: AsyncFetcher):
        self.config = config
        self.fetcher = fetcher

    async def discover(self, max_pages: Optional[int] = None) -> Tuple[List[CandidateDomain], Dict[str, int]]:
        limit_pages = max_pages or self.config.max_discovery_pages
        logger.info(f"[discovery:onshopify] Starting directory crawl (max_pages={limit_pages})...")

        pages_scanned = 0
        detail_urls: List[str] = []
        errors = 0
        seen_detail_paths: Set[str] = set()

        # Step 1: Scan listing pages
        for page_num in range(1, limit_pages + 1):
            page_path = f"/country-websites/IN/{page_num}" if page_num > 1 else "/country-websites/IN/"
            url = f"https://onshopify.com{page_path}"

            res = await self.fetcher.fetch(url, domain_key="onshopify.com")
            if res.status_code != 200:
                logger.warning(f"[discovery:onshopify] Page {page_num} returned status {res.status_code}. Error: {res.error}")
                errors += 1
                if res.status_code == 404 or errors > 5:
                    break
                continue

            pages_scanned += 1
            # Parse detail links
            soup = BeautifulSoup(res.text, "lxml")
            page_detail_count = 0
            for a in soup.find_all("a", href=True):
                raw_href = a.get("href")
                if isinstance(raw_href, list):
                    href = raw_href[0].strip() if raw_href else ""
                elif isinstance(raw_href, str):
                    href = raw_href.strip()
                else:
                    continue

                if href.startswith("/website/shopify-site-"):
                    if href not in seen_detail_paths:
                        seen_detail_paths.add(href)
                        detail_urls.append(f"https://onshopify.com{href}")
                        page_detail_count += 1

            if page_detail_count == 0:
                # No more stores on this page
                break

            # If we already have more than enough candidates for the target, stop scanning listing pages early
            if len(detail_urls) >= self.config.target * self.config.candidate_target_multiplier:
                break

        logger.info(f"[discovery:onshopify] Scanned {pages_scanned} pages, discovered {len(detail_urls)} store detail links. Fetching domains...")

        # Step 2: Concurrently fetch store detail cards to extract candidate domains
        candidates: List[CandidateDomain] = []
        domains_seen: Set[str] = set()
        duplicates = 0

        async def fetch_and_parse_site(site_url: str):
            nonlocal duplicates, errors
            res = await self.fetcher.fetch(site_url, domain_key="onshopify.com")
            if res.status_code != 200 or not res.text:
                errors += 1
                return None

            # Pattern 1: <h1>Shopify store: domain.com</h1>
            m = re.search(r"Shopify store:\s*([a-zA-Z0-9\.\-]+)", res.text, re.IGNORECASE)
            if not m:
                # Pattern 2: <title>domain.com Shopify website sample
                m = re.search(r"<title>([a-zA-Z0-9\.\-]+)\s+Shopify website", res.text, re.IGNORECASE)

            if m:
                raw_dom = m.group(1).strip()
                norm = normalize_domain(raw_dom)
                if norm and is_valid_domain(norm):
                    return norm
            return None

        # Execute in batches to be polite to OnShopify
        batch_size = 20
        for i in range(0, len(detail_urls), batch_size):
            batch = detail_urls[i : i + batch_size]
            tasks = [fetch_and_parse_site(u) for u in batch]
            results = await asyncio.gather(*tasks)

            for dom in results:
                if dom:
                    if dom in domains_seen:
                        duplicates += 1
                    else:
                        domains_seen.add(dom)
                        candidates.append(CandidateDomain(domain=dom, raw_url=f"https://{dom}", source="onshopify"))

            if len(candidates) >= self.config.target * self.config.candidate_target_multiplier:
                break

        stats = {
            "pages_scanned": pages_scanned,
            "urls_found": len(detail_urls),
            "domains_added": len(candidates),
            "duplicates": duplicates,
            "errors": errors,
        }
        logger.info(
            f"[discovery:onshopify] pages_scanned={pages_scanned} urls_found={len(detail_urls)} "
            f"domains_added={len(candidates)} duplicates={duplicates} errors={errors}"
        )
        return candidates, stats


class CommonCrawlDiscovery:
    """
    Queries Common Crawl CDX Index API for Shopify candidate domains.
    Handles network disruptions and rate-limiting gracefully with detailed diagnostics.
    """

    def __init__(self, config: Config, fetcher: AsyncFetcher):
        self.config = config
        self.fetcher = fetcher

    async def discover(self) -> Tuple[List[CandidateDomain], Dict[str, Any]]:
        logger.info("[discovery:common-crawl] Checking Common Crawl collections...")
        candidates: List[CandidateDomain] = []
        stats: Dict[str, Any] = {
            "collection": "unknown",
            "urls_found": 0,
            "domains_added": 0,
            "duplicates": 0,
            "errors": 0,
            "status": "pending"
        }

        collinfo_url = "https://index.commoncrawl.org/collinfo.json"
        res = await self.fetcher.fetch(collinfo_url, domain_key="index.commoncrawl.org")

        if res.status_code != 200 or not res.text:
            err_msg = res.error or f"HTTP {res.status_code}"
            logger.warning(
                f"[discovery:common-crawl] collection=N/A candidates=0 error={err_msg}. "
                "Common Crawl CDX server unavailable; falling back to alternative sources."
            )
            stats["errors"] = 1
            stats["status"] = f"Failed to connect: {err_msg}"
            return candidates, stats

        try:
            import orjson
            collections = orjson.loads(res.text)
            if not collections:
                stats["status"] = "No collections returned"
                return candidates, stats

            latest_col = collections[0]
            cdx_api = latest_col.get("cdx-api")
            col_id = latest_col.get("id", "latest")
            stats["collection"] = col_id

            logger.info(f"[discovery:common-crawl] collection={col_id} querying index for *.myshopify.com...")

            # Query CDX API for myshopify.com domains
            query_url = f"{cdx_api}?url=*.myshopify.com/*&output=json&limit=500&fl=url"
            cdx_res = await self.fetcher.fetch(query_url, domain_key="index.commoncrawl.org")

            if cdx_res.status_code != 200:
                stats["errors"] += 1
                stats["status"] = f"CDX query failed: HTTP {cdx_res.status_code}"
                logger.warning(f"[discovery:common-crawl] collection={col_id} CDX query returned {cdx_res.status_code}")
                return candidates, stats

            domains_seen: Set[str] = set()
            for line in cdx_res.text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = orjson.loads(line)
                    url = data.get("url", "")
                    if url:
                        stats["urls_found"] += 1
                        norm = normalize_domain(url)
                        if norm and is_valid_domain(norm):
                            if norm in domains_seen:
                                stats["duplicates"] += 1
                            else:
                                domains_seen.add(norm)
                                candidates.append(CandidateDomain(domain=norm, raw_url=url, source="common-crawl"))
                except Exception:
                    continue

            stats["domains_added"] = len(candidates)
            stats["status"] = "success"
            logger.info(
                f"[discovery:common-crawl] collection={col_id} urls_found={stats['urls_found']} "
                f"domains_added={stats['domains_added']} errors=0"
            )
            return candidates, stats

        except Exception as e:
            logger.warning(f"[discovery:common-crawl] Error during Common Crawl discovery: {e}")
            stats["errors"] += 1
            stats["status"] = str(e)
            return candidates, stats


class LocalSeedDiscovery:
    """
    Loads candidate domains from local seed files (e.g. data/seeds.txt).
    Ignores blank lines and comments (#).
    """

    def __init__(self, config: Config):
        self.config = config

    def discover(self, file_path: Optional[str] = None) -> Tuple[List[CandidateDomain], Dict[str, int]]:
        target_path = file_path or self.config.seeds_file
        candidates: List[CandidateDomain] = []
        domains_seen: Set[str] = set()
        duplicates = 0
        lines_read = 0

        logger.info(f"[discovery:seeds] Reading seeds from {target_path}...")

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                for line in f:
                    lines_read += 1
                    raw = line.strip()
                    if not raw or raw.startswith("#"):
                        continue

                    norm = normalize_domain(raw)
                    if norm and is_valid_domain(norm):
                        if norm in domains_seen:
                            duplicates += 1
                        else:
                            domains_seen.add(norm)
                            candidates.append(CandidateDomain(domain=norm, raw_url=raw, source="local_seeds"))

        except Exception as e:
            logger.error(f"[discovery:seeds] Failed to read seed file {target_path}: {e}")

        stats = {
            "lines_read": lines_read,
            "domains_added": len(candidates),
            "duplicates": duplicates,
        }
        logger.info(f"[discovery:seeds] lines_read={lines_read} domains_added={len(candidates)} duplicates={duplicates}")
        return candidates, stats


class CandidateDiscoveryManager:
    """
    Coordinates multi-source candidate discovery, normalizes domains,
    deduplicates candidates, and logs clear diagnostic summaries.
    """

    def __init__(self, config: Config, fetcher: AsyncFetcher):
        self.config = config
        self.fetcher = fetcher
        self.onshopify = OnShopifyDiscovery(config, fetcher)
        self.common_crawl = CommonCrawlDiscovery(config, fetcher)
        self.local_seeds = LocalSeedDiscovery(config)

    async def discover_candidates(
        self,
        sources: List[str],
        seed_path: Optional[str] = None,
        max_pages: Optional[int] = None
    ) -> Tuple[List[CandidateDomain], Dict[str, Any]]:
        all_candidates: List[CandidateDomain] = []
        seen_domains: Set[str] = set()
        diagnostics: Dict[str, Any] = {}

        logger.info(f"=== Starting Candidate Discovery (Sources: {sources}) ===")

        # 1. Local seeds
        if "all" in sources or "seeds" in sources or "local" in sources:
            seed_cands, seed_stats = self.local_seeds.discover(seed_path)
            diagnostics["seeds"] = seed_stats
            for c in seed_cands:
                if c.domain not in seen_domains:
                    seen_domains.add(c.domain)
                    all_candidates.append(c)

        # 2. OnShopify Directory
        if "all" in sources or "onshopify" in sources:
            os_cands, os_stats = await self.onshopify.discover(max_pages=max_pages)
            diagnostics["onshopify"] = os_stats
            for c in os_cands:
                if c.domain not in seen_domains:
                    seen_domains.add(c.domain)
                    all_candidates.append(c)

        # 3. Common Crawl
        if "all" in sources or "commoncrawl" in sources or "common-crawl" in sources:
            cc_cands, cc_stats = await self.common_crawl.discover()
            diagnostics["common_crawl"] = cc_stats
            for c in cc_cands:
                if c.domain not in seen_domains:
                    seen_domains.add(c.domain)
                    all_candidates.append(c)

        diagnostics["total_unique_candidates"] = len(all_candidates)

        print("\n" + "="*50)
        print(" Candidate Discovery Diagnostics")
        print("="*50)
        if "seeds" in diagnostics:
            print(f" Local Seeds:        {diagnostics['seeds']['domains_added']} domains (from {diagnostics['seeds']['lines_read']} lines)")
        if "onshopify" in diagnostics:
            print(f" OnShopify:          {diagnostics['onshopify']['domains_added']} domains (from {diagnostics['onshopify']['pages_scanned']} pages, {diagnostics['onshopify']['errors']} errors)")
        if "common_crawl" in diagnostics:
            cc_info = diagnostics['common_crawl']
            print(f" Common Crawl:       {cc_info.get('domains_added', 0)} domains (Status: {cc_info.get('status', 'unknown')})")
        print(f" Total Unique Candidates: {len(all_candidates)}")
        print("="*50 + "\n")

        if len(all_candidates) == 0:
            logger.error(
                "CRITICAL: Discovered 0 unique candidate domains! "
                "Check network connection and source diagnostics above."
            )

        return all_candidates, diagnostics
