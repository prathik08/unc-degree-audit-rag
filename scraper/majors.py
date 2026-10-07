"""Registry of majors to scrape and the department course pages that feed
into their requirements. Department slugs are catalog.unc.edu/courses/<slug>/
and don't always match the obvious abbreviation (political science is "poli",
not "plsc") - verify a new slug with a manual curl before adding it here.

Start with this small set to prove the scraper generalizes across majors in
different departments; add more by copying a row once its slug is verified.
"""

BASE = "https://catalog.unc.edu"

MAJORS = {
    "computer-science-bs": f"{BASE}/undergraduate/programs-study/computer-science-major-bs/",
    "psychology-ba": f"{BASE}/undergraduate/programs-study/psychology-major-ba/",
    "biology-bs": f"{BASE}/undergraduate/programs-study/biology-major-bs/",
    "economics-bs": f"{BASE}/undergraduate/programs-study/economics-major-bs/",
    "political-science-ba": f"{BASE}/undergraduate/programs-study/political-science-major-ba/",
}

DEPARTMENTS = {
    "comp": f"{BASE}/courses/comp/",
    "math": f"{BASE}/courses/math/",
    "stor": f"{BASE}/courses/stor/",
    "psyc": f"{BASE}/courses/psyc/",
    "biol": f"{BASE}/courses/biol/",
    "econ": f"{BASE}/courses/econ/",
    "poli": f"{BASE}/courses/poli/",
}

# Prose policy/explainer pages, parsed by scraper/policy_parser.py and
# embedded for RAG - not the structured major/course format, since these
# answer "what does X mean" rather than "does completed_courses satisfy X".
# Just the core gen-ed page for now; substitution-list and other policy
# pages are a documented future addition, not scraped yet.
POLICY_PAGES = {
    "ideas-in-action-gen-ed": f"{BASE}/undergraduate/ideas-in-action/",
}
