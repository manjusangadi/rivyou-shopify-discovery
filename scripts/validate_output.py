"""
Output validation script for verifying data quality and schema compliance.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.india import CANONICAL_STATES_AND_UTS
from src.utils import normalize_domain, is_valid_domain, is_valid_email

REQUIRED_COLUMNS = [
    "domain_url",
    "all_contacts",
    "socials",
    "category",
    "tagline_description",
    "logo",
    "state"
]


def validate_outputs(
    stores_path: Path,
    audit_path: Path,
    summary_path: Path
):
    print("="*60)
    print(" Rivyou Data Quality & Verification Audit Report")
    print("="*60)

    if not stores_path.exists():
        print(f"[ERROR] stores.csv not found at {stores_path}")
        return False

    with open(stores_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # 1. Verify schema
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing_cols:
            print(f"[FAIL] Schema missing required columns: {missing_cols}")
            return False
        print(f"[PASS] All {len(REQUIRED_COLUMNS)} required columns present: {', '.join(REQUIRED_COLUMNS)}")

        rows = list(reader)

    total_rows = len(rows)
    print(f"Total rows in stores.csv: {total_rows}")

    if total_rows == 0:
        print("[WARNING] stores.csv is empty! Run the pipeline first to generate data.")
        return False

    seen_domains = set()
    duplicate_domains = 0
    invalid_domains = 0
    invalid_states = 0
    favicon_logos = 0
    missing_category = 0
    missing_description = 0
    missing_email = 0
    missing_phone = 0
    missing_socials = 0
    missing_state = 0
    missing_logo = 0

    for r in rows:
        dom = normalize_domain(r.get("domain_url") or "")
        if not dom or not is_valid_domain(dom):
            invalid_domains += 1
        elif dom in seen_domains:
            duplicate_domains += 1
        else:
            seen_domains.add(dom)

        # State validation
        st = (r.get("state") or "").strip()
        if not st:
            missing_state += 1
        elif st not in CANONICAL_STATES_AND_UTS:
            invalid_states += 1

        # Contacts validation
        contacts = (r.get("all_contacts") or "").strip()
        has_email = any("@" in c for c in contacts.split(";")) if contacts else False
        has_phone = any("+" in c or c.isdigit() for c in contacts.split(";")) if contacts else False

        if not has_email:
            missing_email += 1
        if not has_phone:
            missing_phone += 1

        # Socials
        if not (r.get("socials") or "").strip():
            missing_socials += 1

        # Category
        cat = (r.get("category") or "").strip()
        if not cat or cat == "other":
            missing_category += 1

        # Tagline / description
        if not (r.get("tagline_description") or "").strip():
            missing_description += 1

        # Logo
        logo = (r.get("logo") or "").strip().lower()
        if not logo:
            missing_logo += 1
        elif "favicon" in logo or "apple-touch-icon" in logo:
            favicon_logos += 1

    print("\n--- Validation Statistics ---")
    print(f"Total rows:           {total_rows}")
    print(f"Duplicate domains:    {duplicate_domains}")
    print(f"Invalid domains:      {invalid_domains}")
    print(f"Invalid states:       {invalid_states}")
    print(f"Favicon logos:        {favicon_logos}")
    print(f"Missing category:     {missing_category}")
    print(f"Missing description:  {missing_description}")
    print(f"Missing email:        {missing_email}")
    print(f"Missing phone:        {missing_phone}")
    print(f"Missing socials:      {missing_socials}")
    print(f"Missing state:        {missing_state}")
    print(f"Missing logo:         {missing_logo}")

    # Summary JSON validation
    if summary_path.exists():
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
            print("\n--- Summary Verification ---")
            print(f"Candidate count:      {summary.get('candidate_count')}")
            print(f"Unique candidates:    {summary.get('unique_candidate_count')}")
            print(f"Shopify verified:     {summary.get('shopify_verified')}")
            print(f"India verified:       {summary.get('india_verified')}")
            print(f"Final stores:         {summary.get('final_stores')}")
            print(f"Email coverage:       {summary.get('email_coverage', 0)*100:.1f}%")
            print(f"Phone coverage:       {summary.get('phone_coverage', 0)*100:.1f}%")
            print(f"Social coverage:      {summary.get('social_coverage', 0)*100:.1f}%")
            print(f"State coverage:       {summary.get('state_coverage', 0)*100:.1f}%")

    # Critical failure checks
    passed = True
    if duplicate_domains > 0:
        print("[FAIL] Found duplicate domains in stores.csv!")
        passed = False
    if invalid_domains > 0:
        print("[FAIL] Found malformed or invalid domains!")
        passed = False
    if invalid_states > 0:
        print("[FAIL] Found non-canonical state strings!")
        passed = False
    if favicon_logos > 0:
        print("[FAIL] Found favicons accepted as brand logos!")
        passed = False

    if passed:
        print("\n[SUCCESS] Output data passed all strict validation checks!")
    print("="*60)
    return passed


def main():
    parser = argparse.ArgumentParser(description="Validate output data quality.")
    parser.add_argument("--stores", type=str, default="data/output/stores.csv")
    parser.add_argument("--audit", type=str, default="data/output/audit.csv")
    parser.add_argument("--summary", type=str, default="data/output/summary.json")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    stores_path = project_root / args.stores
    audit_path = project_root / args.audit
    summary_path = project_root / args.summary

    success = validate_outputs(stores_path, audit_path, summary_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
