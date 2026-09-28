"""
CLI entry point for running the Rivyou Shopify India Discovery Pipeline.
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import Config
from src.pipeline import Pipeline


def setup_logging(level: str = "INFO"):
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Rivyou SDE Intern Technical Assignment: Indian Shopify Store Discovery & Verification Pipeline"
    )
    parser.add_argument(
        "--target",
        type=int,
        default=1000,
        help="Target number of verified Indian Shopify stores to discover (default: 1000)"
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=10,
        help="Maximum concurrent async network requests (default: 10)"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="all",
        choices=["all", "onshopify", "commoncrawl", "seeds"],
        help="Candidate discovery source to use: 'all', 'onshopify', 'commoncrawl', 'seeds' (default: all)"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/seeds.txt",
        help="Path to custom seed domains file (default: data/seeds.txt)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="Maximum pagination depth to crawl on directory sources (default: 100)"
    )
    parser.add_argument(
        "--shopify-threshold",
        type=int,
        default=5,
        help="Score threshold for Shopify storefront verification (default: 5)"
    )
    parser.add_argument(
        "--india-threshold",
        type=int,
        default=7,
        help="Score threshold for India business verification (default: 7)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    setup_logging(args.log_level)

    config = Config(
        max_concurrency=args.max_concurrency,
        shopify_threshold=args.shopify_threshold,
        india_threshold=args.india_threshold,
        max_discovery_pages=args.max_pages,
        target=args.target
    )

    sources = [args.source] if args.source != "all" else ["seeds", "onshopify", "commoncrawl"]

    pipeline = Pipeline(config=config)

    try:
        asyncio.run(
            pipeline.run(
                target=args.target,
                sources=sources,
                seed_path=args.input,
                max_pages=args.max_pages
            )
        )
    except KeyboardInterrupt:
        print("\n[!] Pipeline interrupted by user. Partial results saved.")
    except Exception as e:
        logging.exception(f"[!] Fatal pipeline error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
