"""
Pipeline configuration management.
"""
from dataclasses import dataclass, field
import os
from pathlib import Path


@dataclass
class Config:
    # Concurrency and networking
    max_concurrency: int = 10
    request_timeout: float = 15.0
    max_retries: int = 2
    request_delay: float = 0.2
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    # Verification thresholds
    shopify_threshold: int = 5
    india_threshold: int = 7

    # Discovery options
    max_discovery_pages: int = 100
    candidate_target_multiplier: float = 2.5

    # Target number of verified stores
    target: int = 1000

    # Paths
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    data_dir: Path = field(init=False)
    seeds_file: Path = field(init=False)
    output_dir: Path = field(init=False)
    stores_csv: Path = field(init=False)
    audit_csv: Path = field(init=False)
    summary_json: Path = field(init=False)

    def __post_init__(self):
        # Override from environment variables if present
        self.max_concurrency = int(os.getenv("MAX_CONCURRENCY", str(self.max_concurrency)))
        self.request_timeout = float(os.getenv("REQUEST_TIMEOUT", str(self.request_timeout)))
        self.max_retries = int(os.getenv("MAX_RETRIES", str(self.max_retries)))
        self.request_delay = float(os.getenv("REQUEST_DELAY", str(self.request_delay)))
        self.shopify_threshold = int(os.getenv("SHOPIFY_THRESHOLD", str(self.shopify_threshold)))
        self.india_threshold = int(os.getenv("INDIA_THRESHOLD", str(self.india_threshold)))
        self.max_discovery_pages = int(os.getenv("MAX_DISCOVERY_PAGES", str(self.max_discovery_pages)))
        self.user_agent = os.getenv("USER_AGENT", self.user_agent)

        self.data_dir = self.project_root / "data"
        self.seeds_file = Path(os.getenv("SEEDS_FILE", str(self.data_dir / "seeds.txt")))
        self.output_dir = Path(os.getenv("OUTPUT_DIR", str(self.data_dir / "output")))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.stores_csv = self.output_dir / "stores.csv"
        self.audit_csv = self.output_dir / "audit.csv"
        self.summary_json = self.output_dir / "summary.json"


# Default global instance
default_config = Config()
