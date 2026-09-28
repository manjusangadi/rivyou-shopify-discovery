"""
Robots.txt parsing, validation, and caching.
"""
import logging
from typing import Dict, Optional
from urllib.parse import urlparse
import urllib.robotparser
import httpx

logger = logging.getLogger(__name__)


class RobotsChecker:
    """
    Manages and caches RobotFileParser instances per domain to respect robots.txt.
    """

    def __init__(self, user_agent: str = "*", request_timeout: float = 10.0):
        self.user_agent = user_agent
        self.request_timeout = request_timeout
        self._cache: Dict[str, urllib.robotparser.RobotFileParser] = {}

    async def get_parser(self, client: httpx.AsyncClient, domain: str) -> urllib.robotparser.RobotFileParser:
        """
        Fetches and caches the RobotFileParser for a domain.
        """
        if domain in self._cache:
            return self._cache[domain]

        rp = urllib.robotparser.RobotFileParser()
        robots_url = f"https://{domain}/robots.txt"

        try:
            resp = await client.get(robots_url, timeout=self.request_timeout)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                # 404 or non-200 generally implies no crawling restrictions
                rp.parse([])
        except Exception as e:
            logger.debug(f"[robots.txt] Failed to fetch robots.txt for {domain}: {e}. Allowing access.")
            rp.parse([])

        self._cache[domain] = rp
        return rp

    async def is_allowed(self, client: httpx.AsyncClient, domain: str, path: str = "/") -> bool:
        """
        Checks if fetching the specified path on domain is permitted by robots.txt.
        """
        try:
            rp = await self.get_parser(client, domain)
            target_url = f"https://{domain}{path if path.startswith('/') else '/' + path}"
            allowed = rp.can_fetch(self.user_agent, target_url)
            # Fallback check for wildcard user-agent
            if not allowed:
                allowed = rp.can_fetch("*", target_url)
            return allowed
        except Exception as e:
            logger.debug(f"[robots.txt] Error checking permissions for {domain}{path}: {e}")
            return True
