"""CLI entrypoint: scrapes every major, department, and policy page in
scraper/majors.py into data/majors/*.json, data/courses/*.json, and
data/policy/*.json.

Usage: python -m scraper.run_scrape
"""

from pathlib import Path

from scraper.course_parser import save_department
from scraper.major_parser import save_major
from scraper.majors import DEPARTMENTS, MAJORS, POLICY_PAGES
from scraper.policy_parser import save_policy_page

DATA_DIR = Path(__file__).parent.parent / "data"


def main() -> None:
    print(f"Scraping {len(MAJORS)} majors...")
    for slug, url in MAJORS.items():
        out_path = save_major(url, DATA_DIR / "majors", slug)
        print(f"  {slug} -> {out_path}")

    print(f"\nScraping {len(DEPARTMENTS)} department course listings...")
    for slug, url in DEPARTMENTS.items():
        out_path = save_department(url, DATA_DIR / "courses")
        print(f"  {slug} -> {out_path}")

    print(f"\nScraping {len(POLICY_PAGES)} policy pages...")
    for slug, url in POLICY_PAGES.items():
        out_path = save_policy_page(url, DATA_DIR / "policy", slug)
        print(f"  {slug} -> {out_path}")


if __name__ == "__main__":
    main()
