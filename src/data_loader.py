"""
Load and parse BLS Occupational Outlook Handbook XML data.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from html.parser import HTMLParser


@dataclass
class Occupation:
    """Represents a single occupation from the BLS data."""
    code: str
    title: str
    description: str
    soc_codes: list[str] = field(default_factory=list)

    # Quick facts
    median_pay_annual: Optional[int] = None
    median_pay_hourly: Optional[float] = None
    entry_level_education: str = ""
    work_experience: str = ""
    on_the_job_training: str = ""
    number_of_jobs: Optional[int] = None
    employment_outlook: str = ""
    employment_outlook_value: Optional[int] = None
    employment_openings: Optional[int] = None

    # Detailed sections (HTML stripped)
    what_they_do: str = ""
    work_environment: str = ""
    how_to_become_one: str = ""
    pay_details: str = ""
    job_outlook_details: str = ""

    # State/area resources
    state_area_links: list[str] = field(default_factory=list)

    # Similar occupations (list of (title, code, education, salary) tuples)
    similar_occupations: list[tuple[str, str, str, str]] = field(default_factory=list)

    # Category (derived from occupation code prefix)
    category: str = ""

    # BLS OOH handbook URL
    url: str = ""


class HTMLStripper(HTMLParser):
    """Strip HTML tags and extract text content."""

    def __init__(self):
        super().__init__()
        self.reset()
        self.text_parts = []

    def handle_data(self, data):
        self.text_parts.append(data)

    def get_text(self) -> str:
        return " ".join(self.text_parts)


def strip_html(html_content: str) -> str:
    """Remove HTML tags and return plain text."""
    if not html_content:
        return ""
    stripper = HTMLStripper()
    try:
        stripper.feed(html_content)
        text = stripper.get_text()
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    except Exception:
        return html_content


def extract_similar_occupations(html_content: str) -> list[tuple[str, str, str, str]]:
    """Extract similar occupation data from HTML table."""
    similar = []
    if not html_content:
        return similar

    # Extract href and title from occupation links
    # Pattern: <a href="/ooh/category/occupation.htm">Title</a>
    link_pattern = r'<a href="/ooh/([^"]+)"[^>]*>\s*([^<]+)</a>'

    # Find table rows
    row_pattern = r'<tr>(.*?)</tr>'
    rows = re.findall(row_pattern, html_content, re.DOTALL)

    for row in rows:
        # Skip header rows
        if '<th>' in row:
            continue

        # Extract occupation link and title
        link_match = re.search(link_pattern, row)
        if not link_match:
            continue

        href = link_match.group(1)
        title = link_match.group(2).strip()

        # Extract code from href (e.g., "business-and-financial/budget-analysts.htm")
        code_match = re.search(r'([^/]+)\.htm', href)
        code = code_match.group(1) if code_match else ""

        # Extract education (in span with title)
        edu_match = re.search(r'<span title="[^"]*">\s*([^<]+)</span>', row)
        education = edu_match.group(1).strip() if edu_match else ""

        # Extract salary (last span with title containing number)
        salary_matches = re.findall(r'<span title="(\d+)">\$?([\d,]+)</span>', row)
        salary = f"${salary_matches[-1][1]}" if salary_matches else ""

        if title and code:
            similar.append((title, code, education, salary))

    return similar


def extract_state_links(html_content: str) -> list[str]:
    """Extract state/area resource links from HTML."""
    links = []
    if not html_content:
        return links

    # Extract all href links
    link_pattern = r'<a[^>]+href="([^"]+)"[^>]*>'
    matches = re.findall(link_pattern, html_content)

    for url in matches:
        if url.startswith('http'):
            links.append(url)

    return links


def extract_category_from_citation(citation_text: str) -> str:
    """Extract category from the citation URL.

    The citation contains a URL like:
    https://www.bls.gov/ooh/business-and-financial/accountants-and-auditors.htm
    We extract 'business-and-financial' as the category.
    """
    if not citation_text:
        return "other"

    # Pattern: bls.gov/ooh/{category}/{occupation}.htm
    match = re.search(r'bls\.gov/ooh/([^/]+)/[^/]+\.htm', citation_text)
    if match:
        return match.group(1)
    return "other"


def get_element_text(element: Optional[ET.Element], default: str = "") -> str:
    """Safely extract text from an XML element."""
    if element is None:
        return default
    return element.text.strip() if element.text else default


def get_element_int(element: Optional[ET.Element], default: Optional[int] = None) -> Optional[int]:
    """Safely extract integer from an XML element."""
    if element is None:
        return default
    try:
        return int(element.text.strip()) if element.text else default
    except (ValueError, AttributeError):
        return default


def get_element_float(element: Optional[ET.Element], default: Optional[float] = None) -> Optional[float]:
    """Safely extract float from an XML element."""
    if element is None:
        return default
    try:
        return float(element.text.strip()) if element.text else default
    except (ValueError, AttributeError):
        return default


def parse_occupation(occ_elem: ET.Element) -> Optional[Occupation]:
    """Parse a single occupation element from XML."""
    code = get_element_text(occ_elem.find('occupation_code'))
    title = get_element_text(occ_elem.find('title'))

    if not code or not title:
        return None

    # Extract SOC codes
    soc_codes = []
    soc_coverage = occ_elem.find('soc_coverage')
    if soc_coverage is not None:
        for soc in soc_coverage.findall('soc_code'):
            if soc.text:
                soc_codes.append(soc.text.strip())

    # Quick facts
    qf = occ_elem.find('quick_facts')

    median_annual = None
    median_hourly = None
    education = ""
    experience = ""
    training = ""
    num_jobs = None
    outlook = ""
    outlook_value = None
    openings = None

    if qf is not None:
        # Median pay
        pay_annual = qf.find('qf_median_pay_annual')
        if pay_annual is not None:
            median_annual = get_element_int(pay_annual.find('value'))

        pay_hourly = qf.find('qf_median_pay_hourly')
        if pay_hourly is not None:
            median_hourly = get_element_float(pay_hourly.find('value'))

        # Education
        edu_elem = qf.find('qf_entry_level_education')
        if edu_elem is not None:
            education = get_element_text(edu_elem.find('value'))

        # Experience
        exp_elem = qf.find('qf_work_experience')
        if exp_elem is not None:
            experience = get_element_text(exp_elem.find('value'))

        # Training
        train_elem = qf.find('qf_on_the_job_training')
        if train_elem is not None:
            training = get_element_text(train_elem.find('value'))

        # Number of jobs
        jobs_elem = qf.find('qf_number_of_jobs')
        if jobs_elem is not None:
            num_jobs = get_element_int(jobs_elem.find('value'))

        # Outlook
        outlook_elem = qf.find('qf_employment_outlook')
        if outlook_elem is not None:
            outlook = get_element_text(outlook_elem.find('description'))
            outlook_value = get_element_int(outlook_elem.find('value'))

        # Openings
        openings_elem = qf.find('qf_employment_openings')
        if openings_elem is not None:
            openings = get_element_int(openings_elem.find('value'))

    # Detailed sections
    what_they_do_elem = occ_elem.find('what_they_do/section_body')
    what_they_do = strip_html(get_element_text(what_they_do_elem)) if what_they_do_elem is not None else ""

    work_env_elem = occ_elem.find('work_environment/section_body')
    work_environment = strip_html(get_element_text(work_env_elem)) if work_env_elem is not None else ""

    how_to_elem = occ_elem.find('how_to_become_one/section_body')
    how_to_become_one = strip_html(get_element_text(how_to_elem)) if how_to_elem is not None else ""

    pay_elem = occ_elem.find('pay/section_body')
    pay_details = strip_html(get_element_text(pay_elem)) if pay_elem is not None else ""

    outlook_elem = occ_elem.find('job_outlook/section_body')
    job_outlook_details = strip_html(get_element_text(outlook_elem)) if outlook_elem is not None else ""

    # State/area links
    state_elem = occ_elem.find('state_and_area/section_body')
    state_links = extract_state_links(get_element_text(state_elem)) if state_elem is not None else []

    # Similar occupations
    similar_elem = occ_elem.find('similar_occupations/section_body')
    similar = extract_similar_occupations(get_element_text(similar_elem)) if similar_elem is not None else []

    # Extract category and URL from citation
    citation_elem = occ_elem.find('citation')
    citation_text = get_element_text(citation_elem) if citation_elem is not None else ""
    category = extract_category_from_citation(citation_text)

    # Extract the BLS URL from citation text
    url_match = re.search(r'(https?://www\.bls\.gov/ooh/[^\s]+\.htm)', citation_text)
    ooh_url = url_match.group(1) if url_match else ""

    return Occupation(
        code=code,
        title=title,
        description=get_element_text(occ_elem.find('description')),
        soc_codes=soc_codes,
        median_pay_annual=median_annual,
        median_pay_hourly=median_hourly,
        entry_level_education=education,
        work_experience=experience,
        on_the_job_training=training,
        number_of_jobs=num_jobs,
        employment_outlook=outlook,
        employment_outlook_value=outlook_value,
        employment_openings=openings,
        what_they_do=what_they_do,
        work_environment=work_environment,
        how_to_become_one=how_to_become_one,
        pay_details=pay_details,
        job_outlook_details=job_outlook_details,
        state_area_links=state_links,
        similar_occupations=similar,
        category=category,
        url=ooh_url,
    )


def load_occupations(xml_path: str | Path) -> list[Occupation]:
    """Load all occupations from the BLS XML file."""
    xml_path = Path(xml_path)

    if not xml_path.exists():
        raise FileNotFoundError(f"XML file not found: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    occupations = []
    for occ_elem in root.findall('.//occupation'):
        occ = parse_occupation(occ_elem)
        if occ:
            occupations.append(occ)

    return occupations


if __name__ == "__main__":
    # Test loading
    from pathlib import Path

    xml_path = Path(__file__).parent.parent / "data" / "xml-compilation.xml"
    occupations = load_occupations(xml_path)

    print(f"Loaded {len(occupations)} occupations")

    # Show sample
    if occupations:
        occ = occupations[0]
        print(f"\nSample: {occ.title}")
        print(f"  Code: {occ.code}")
        print(f"  Category: {occ.category}")
        print(f"  Education: {occ.entry_level_education}")
        print(f"  Salary: ${occ.median_pay_annual:,}" if occ.median_pay_annual else "  Salary: N/A")
        print(f"  Outlook: {occ.employment_outlook}")
        print(f"  State links: {len(occ.state_area_links)}")
        print(f"  Similar: {len(occ.similar_occupations)}")
