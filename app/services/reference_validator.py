"""
Reference Validator Service (v4.0)
Validates DOIs, detects duplicates, and generates Reference QA Reports
"""
import re
import logging
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import asyncio

import requests
from fuzzywuzzy import fuzz

logger = logging.getLogger(__name__)


class ReferenceValidator:
    """Reference validation and QA service"""

    def __init__(self, cache_ttl: int = 86400, api_timeout: int = 10):
        """
        Initialize Reference Validator

        Args:
            cache_ttl: Cache TTL in seconds (default 24 hours)
            api_timeout: API timeout in seconds (default 10s)
        """
        self.cache_ttl = cache_ttl
        self.api_timeout = api_timeout
        self.doi_cache: Dict[str, Tuple[bool, datetime]] = {}

        # DOI validation patterns
        self.doi_pattern = re.compile(
            r'10\.\d{4,9}/[-._;()/:A-Za-z0-9]+',
            re.IGNORECASE
        )

        # Publisher URL patterns
        self.publisher_patterns = {
            'arxiv': re.compile(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', re.IGNORECASE),
            'ieee': re.compile(r'ieeexplore\.ieee\.org/document/(\d+)', re.IGNORECASE),
            'acm': re.compile(r'dl\.acm\.org/doi/(?:abs/)?10\.\d+/\d+', re.IGNORECASE),
            'springer': re.compile(r'link\.springer\.com/(?:article|chapter)/10\.\d+', re.IGNORECASE),
            'pubmed': re.compile(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', re.IGNORECASE),
            'nature': re.compile(r'nature\.com/articles/[a-z0-9-]+', re.IGNORECASE),
            'science': re.compile(r'science\.org/doi/10\.\d+', re.IGNORECASE),
        }

    def extract_doi(self, text: str) -> Optional[str]:
        """
        Extract DOI from text

        Args:
            text: Text containing potential DOI

        Returns:
            str: Extracted DOI or None
        """
        match = self.doi_pattern.search(text)
        if match:
            doi = match.group(0)
            # Clean up DOI
            doi = doi.rstrip('.,;:')
            return doi
        return None

    def extract_publisher_id(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Extract publisher and ID from URL

        Args:
            url: Publisher URL

        Returns:
            Tuple[str, str]: (publisher_name, id) or None
        """
        for publisher, pattern in self.publisher_patterns.items():
            match = pattern.search(url)
            if match:
                if match.groups():
                    return (publisher, match.group(1))
                else:
                    return (publisher, url)
        return None

    async def validate_doi(self, doi: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Validate DOI using multiple methods (SOP v4.0 Enhanced)
        1. DOI.org API
        2. CrossRef API (fallback)
        3. Format validation

        Args:
            doi: DOI to validate
            use_cache: Whether to use cache

        Returns:
            Dict with validation results
        """
        # Check cache
        if use_cache and doi in self.doi_cache:
            cached_result, cached_time = self.doi_cache[doi]
            if datetime.now() - cached_time < timedelta(seconds=self.cache_ttl):
                logger.debug(f"DOI cache hit: {doi}")
                return {
                    "doi": doi,
                    "valid": cached_result,
                    "cached": True,
                    "metadata": None,
                    "method": "cache"
                }

        # Validate DOI format
        if not self.doi_pattern.match(doi):
            logger.warning(f"Invalid DOI format: {doi}")
            return {
                "doi": doi,
                "valid": False,
                "error": "Invalid DOI format",
                "cached": False,
                "method": "format_check"
            }

        # Check for placeholder DOIs (SOP v4.0 requirement)
        placeholder_patterns = [
            r'10\.\d+/xxx',  # 10.1109/xxx
            r'10\.xxxx/',    # 10.xxxx/
            r'10\.\d+/\w*\.{3}',  # 10.1109/...
        ]
        for pattern in placeholder_patterns:
            if re.search(pattern, doi, re.IGNORECASE):
                logger.warning(f"Placeholder DOI detected: {doi}")
                return {
                    "doi": doi,
                    "valid": False,
                    "error": "Placeholder DOI not allowed (SOP v4.0)",
                    "cached": False,
                    "method": "placeholder_check"
                }

        # Method 1: Try DOI.org API
        try:
            url = f"https://doi.org/api/handles/{doi}"
            response = await asyncio.to_thread(
                requests.get,
                url,
                timeout=self.api_timeout,
                headers={"Accept": "application/json"}
            )

            if response.status_code == 200:
                data = response.json()
                # Cache result
                self.doi_cache[doi] = (True, datetime.now())

                return {
                    "doi": doi,
                    "valid": True,
                    "metadata": {
                        "handle": data.get("handle"),
                        "responseCode": data.get("responseCode")
                    },
                    "cached": False,
                    "method": "doi.org"
                }

        except Exception as e:
            logger.debug(f"DOI.org API failed for {doi}: {e}, trying CrossRef...")

        # Method 2: Try CrossRef API (fallback)
        try:
            url = f"https://api.crossref.org/works/{doi}"
            response = await asyncio.to_thread(
                requests.get,
                url,
                timeout=self.api_timeout,
                headers={"Accept": "application/json"}
            )

            if response.status_code == 200:
                data = response.json()
                # Cache result
                self.doi_cache[doi] = (True, datetime.now())

                return {
                    "doi": doi,
                    "valid": True,
                    "metadata": {
                        "title": data.get("message", {}).get("title", [None])[0],
                        "publisher": data.get("message", {}).get("publisher"),
                        "type": data.get("message", {}).get("type")
                    },
                    "cached": False,
                    "method": "crossref"
                }

        except Exception as e:
            logger.debug(f"CrossRef API failed for {doi}: {e}")

        # All methods failed
        logger.warning(f"DOI validation failed for {doi}")
        self.doi_cache[doi] = (False, datetime.now())
        return {
            "doi": doi,
            "valid": False,
            "error": "DOI not found in DOI.org or CrossRef",
            "cached": False,
            "method": "all_failed"
        }

    async def validate_publisher_url(self, url: str) -> Dict[str, Any]:
        """
        Validate publisher URL (SOP v4.0 Enhanced)
        Checks if publisher page is accessible

        Args:
            url: Publisher URL

        Returns:
            Dict with validation results
        """
        publisher_info = self.extract_publisher_id(url)

        if not publisher_info:
            # Try generic URL validation
            try:
                response = await asyncio.to_thread(
                    requests.head,
                    url,
                    timeout=self.api_timeout,
                    allow_redirects=True
                )

                return {
                    "url": url,
                    "valid": response.status_code < 400,
                    "publisher": "unknown",
                    "status_code": response.status_code,
                    "accessible": response.status_code < 400
                }

            except Exception as e:
                logger.error(f"URL validation error: {url} - {e}")
                return {
                    "url": url,
                    "valid": False,
                    "publisher": "unknown",
                    "error": str(e),
                    "accessible": False
                }

        publisher, pub_id = publisher_info

        # Check if URL is accessible (HEAD request first, then GET if needed)
        try:
            # Try HEAD first (faster)
            response = await asyncio.to_thread(
                requests.head,
                url,
                timeout=self.api_timeout,
                allow_redirects=True
            )

            accessible = response.status_code < 400

            # If HEAD fails, try GET (some servers don't support HEAD)
            if not accessible:
                response = await asyncio.to_thread(
                    requests.get,
                    url,
                    timeout=self.api_timeout,
                    allow_redirects=True
                )
                accessible = response.status_code < 400

            return {
                "url": url,
                "valid": accessible,
                "publisher": publisher,
                "id": pub_id,
                "status_code": response.status_code,
                "accessible": accessible,
                "final_url": response.url if hasattr(response, 'url') else url
            }

        except requests.Timeout:
            logger.error(f"Publisher URL timeout: {url}")
            return {
                "url": url,
                "valid": False,
                "publisher": publisher,
                "id": pub_id,
                "error": "Timeout",
                "accessible": False
            }
        except Exception as e:
            logger.error(f"Publisher URL validation error: {url} - {e}")
            return {
                "url": url,
                "valid": False,
                "publisher": publisher,
                "id": pub_id,
                "error": str(e),
                "accessible": False
            }

    def detect_duplicates(self, references: List[Dict[str, Any]]) -> List[Tuple[int, int, float]]:
        """
        Detect duplicate references using fuzzy matching

        Args:
            references: List of reference dicts with 'title' and optionally 'doi'

        Returns:
            List of (index1, index2, similarity_score) tuples for duplicates
        """
        duplicates = []

        for i in range(len(references)):
            for j in range(i + 1, len(references)):
                ref1 = references[i]
                ref2 = references[j]

                # Check DOI match (exact)
                if ref1.get('doi') and ref2.get('doi'):
                    if ref1['doi'] == ref2['doi']:
                        duplicates.append((i, j, 1.0))
                        continue

                # Check title similarity (fuzzy)
                title1 = ref1.get('title', '').lower().strip()
                title2 = ref2.get('title', '').lower().strip()

                if title1 and title2:
                    similarity = fuzz.ratio(title1, title2) / 100.0
                    if similarity >= 0.85:  # 85% similarity threshold
                        duplicates.append((i, j, similarity))

        return duplicates

    def compute_reference_hash(self, reference: Dict[str, Any]) -> str:
        """
        Compute hash for reference (for deduplication)

        Args:
            reference: Reference dict

        Returns:
            str: MD5 hash
        """
        # Use DOI if available, otherwise use title
        if reference.get('doi'):
            key = reference['doi'].lower().strip()
        elif reference.get('title'):
            key = reference['title'].lower().strip()
        else:
            key = str(reference)

        return hashlib.md5(key.encode('utf-8')).hexdigest()

    async def validate_references(self, references: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate a list of references (SOP v4.0 Enhanced)
        Validates DOIs, publisher URLs, and detects duplicates

        Args:
            references: List of reference dicts with 'title', 'doi', 'url', etc.

        Returns:
            Dict with validation report
        """
        logger.info(f"Validating {len(references)} references...")

        report = {
            "total_count": len(references),
            "valid_doi_count": 0,
            "invalid_doi_count": 0,
            "no_doi_count": 0,
            "placeholder_doi_count": 0,  # SOP v4.0 NEW
            "valid_url_count": 0,
            "invalid_url_count": 0,
            "no_url_count": 0,
            "duplicate_count": 0,
            "duplicates": [],
            "invalid_dois": [],
            "invalid_urls": [],
            "placeholder_dois": [],  # SOP v4.0 NEW
            "doi_parseability": 0.0,
            "url_accessibility": 0.0,  # SOP v4.0 NEW
            "validation_timestamp": datetime.now().isoformat()
        }

        # Validate DOIs
        doi_tasks = []
        for i, ref in enumerate(references):
            doi = ref.get('doi')
            if not doi:
                # Try to extract DOI from text
                text = f"{ref.get('title', '')} {ref.get('url', '')}"
                doi = self.extract_doi(text)
                if doi:
                    ref['doi'] = doi

            if doi:
                doi_tasks.append((i, self.validate_doi(doi)))
            else:
                report["no_doi_count"] += 1

        # Run DOI validations concurrently
        if doi_tasks:
            results = await asyncio.gather(*[task for _, task in doi_tasks], return_exceptions=True)

            for (i, _), result in zip(doi_tasks, results):
                if isinstance(result, Exception):
                    logger.error(f"DOI validation exception for ref {i}: {result}")
                    report["invalid_doi_count"] += 1
                elif result.get("valid"):
                    report["valid_doi_count"] += 1
                else:
                    report["invalid_doi_count"] += 1
                    report["invalid_dois"].append({
                        "index": i,
                        "doi": result.get("doi"),
                        "error": result.get("error"),
                        "method": result.get("method")
                    })

                    # Track placeholder DOIs separately (SOP v4.0)
                    if result.get("method") == "placeholder_check":
                        report["placeholder_doi_count"] += 1
                        report["placeholder_dois"].append({
                            "index": i,
                            "doi": result.get("doi")
                        })

        # Calculate DOI parseability
        total_with_doi = report["valid_doi_count"] + report["invalid_doi_count"]
        if total_with_doi > 0:
            report["doi_parseability"] = report["valid_doi_count"] / total_with_doi
        else:
            report["doi_parseability"] = 0.0

        # Validate publisher URLs (SOP v4.0 Enhanced)
        url_tasks = []
        for i, ref in enumerate(references):
            url = ref.get('url')
            if url:
                url_tasks.append((i, self.validate_publisher_url(url)))
            else:
                report["no_url_count"] += 1

        # Run URL validations concurrently
        if url_tasks:
            results = await asyncio.gather(*[task for _, task in url_tasks], return_exceptions=True)

            for (i, _), result in zip(url_tasks, results):
                if isinstance(result, Exception):
                    logger.error(f"URL validation exception for ref {i}: {result}")
                    report["invalid_url_count"] += 1
                elif result.get("accessible"):
                    report["valid_url_count"] += 1
                else:
                    report["invalid_url_count"] += 1
                    report["invalid_urls"].append({
                        "index": i,
                        "url": result.get("url"),
                        "error": result.get("error"),
                        "publisher": result.get("publisher")
                    })

        # Calculate URL accessibility
        total_with_url = report["valid_url_count"] + report["invalid_url_count"]
        if total_with_url > 0:
            report["url_accessibility"] = report["valid_url_count"] / total_with_url
        else:
            report["url_accessibility"] = 0.0

        # Detect duplicates
        duplicates = self.detect_duplicates(references)
        report["duplicate_count"] = len(duplicates)
        report["duplicates"] = [
            {
                "index1": i,
                "index2": j,
                "similarity": similarity,
                "title1": references[i].get('title', 'N/A'),
                "title2": references[j].get('title', 'N/A')
            }
            for i, j, similarity in duplicates
        ]

        logger.info(f"Validation complete: {report['valid_doi_count']}/{total_with_doi} valid DOIs, "
                   f"{report['valid_url_count']}/{total_with_url} accessible URLs, "
                   f"{report['duplicate_count']} duplicates, "
                   f"{report['placeholder_doi_count']} placeholder DOIs")

        return report

    def generate_qa_report(self, report: Dict[str, Any], references: List[Dict[str, Any]]) -> str:
        """
        Generate Reference QA Report in Markdown format (SOP v4.0 Enhanced)

        Args:
            report: Validation report from validate_references()
            references: Original reference list

        Returns:
            str: Markdown report
        """
        md = f"""# Reference QA Report (SOP v4.0)

**Generated:** {report['validation_timestamp']}
**Total References:** {report['total_count']}

---

## Summary

| Metric | Count | Percentage |
|--------|-------|------------|
| Valid DOIs | {report['valid_doi_count']} | {report['valid_doi_count']/report['total_count']*100:.1f}% |
| Invalid DOIs | {report['invalid_doi_count']} | {report['invalid_doi_count']/report['total_count']*100:.1f}% |
| Placeholder DOIs | {report.get('placeholder_doi_count', 0)} | {report.get('placeholder_doi_count', 0)/report['total_count']*100:.1f}% |
| No DOI | {report['no_doi_count']} | {report['no_doi_count']/report['total_count']*100:.1f}% |
| Accessible URLs | {report.get('valid_url_count', 0)} | {report.get('valid_url_count', 0)/report['total_count']*100:.1f}% |
| Inaccessible URLs | {report.get('invalid_url_count', 0)} | {report.get('invalid_url_count', 0)/report['total_count']*100:.1f}% |
| Duplicates | {report['duplicate_count']} | {report['duplicate_count']/report['total_count']*100:.1f}% |

**DOI Parseability:** {report['doi_parseability']*100:.1f}%
**URL Accessibility:** {report.get('url_accessibility', 0)*100:.1f}%

---

## Gate 1.6 Status (SOP v4.0)

"""
        # Check Gate 1.6 criteria
        gate_pass = True
        gate_issues = []

        if report['total_count'] < 20:
            gate_pass = False
            gate_issues.append(f"❌ Literature count < 20 (current: {report['total_count']})")
        else:
            md += f"✅ Literature count >= 20 (current: {report['total_count']})\n"

        if report['doi_parseability'] < 0.95:
            gate_pass = False
            gate_issues.append(f"❌ DOI parseability < 95% (current: {report['doi_parseability']*100:.1f}%)")
        else:
            md += f"✅ DOI parseability >= 95% (current: {report['doi_parseability']*100:.1f}%)\n"

        # SOP v4.0: No placeholder DOIs allowed
        if report.get('placeholder_doi_count', 0) > 0:
            gate_pass = False
            gate_issues.append(f"❌ Found {report['placeholder_doi_count']} placeholder DOI(s) (SOP v4.0: not allowed)")
        else:
            md += "✅ No placeholder DOIs found\n"

        if report['duplicate_count'] > 0:
            gate_pass = False
            gate_issues.append(f"❌ Found {report['duplicate_count']} duplicate(s)")
        else:
            md += "✅ No duplicates found\n"

        # SOP v4.0: Check URL accessibility
        if report.get('url_accessibility', 0) < 0.80:
            gate_pass = False
            gate_issues.append(f"⚠️ URL accessibility < 80% (current: {report.get('url_accessibility', 0)*100:.1f}%)")
        else:
            md += f"✅ URL accessibility >= 80% (current: {report.get('url_accessibility', 0)*100:.1f}%)\n"

        md += f"\n**Gate 1.6 Verdict:** {'✅ PASS' if gate_pass else '❌ FAIL'}\n\n"

        if gate_issues:
            md += "**Issues to Fix:**\n"
            for issue in gate_issues:
                md += f"- {issue}\n"
            md += "\n"

        md += "---\n\n"

        # Placeholder DOIs section (SOP v4.0)
        if report.get('placeholder_dois'):
            md += "## ❌ Placeholder DOIs (SOP v4.0: NOT ALLOWED)\n\n"
            md += "**CRITICAL:** SOP v4.0 forbids placeholder DOIs like `10.1109/xxx.2024.1`. Use real DOIs or mark as UNKNOWN.\n\n"
            for item in report['placeholder_dois']:
                md += f"- **[{item['index']}]** `{item['doi']}`\n"
            md += "\n---\n\n"

        # Invalid DOIs section
        if report['invalid_dois']:
            md += "## Invalid DOIs\n\n"
            for item in report['invalid_dois']:
                md += f"- **[{item['index']}]** `{item['doi']}` - {item['error']} (method: {item.get('method', 'unknown')})\n"
            md += "\n---\n\n"

        # Invalid URLs section (SOP v4.0)
        if report.get('invalid_urls'):
            md += "## Inaccessible Publisher URLs\n\n"
            for item in report['invalid_urls']:
                md += f"- **[{item['index']}]** {item['url']} - {item.get('error', 'Not accessible')} (publisher: {item.get('publisher', 'unknown')})\n"
            md += "\n---\n\n"

        # Duplicates section
        if report['duplicates']:
            md += "## Duplicate References\n\n"
            for dup in report['duplicates']:
                md += f"### Duplicate Pair (Similarity: {dup['similarity']*100:.1f}%)\n\n"
                md += f"**[{dup['index1']}]** {dup['title1']}\n\n"
                md += f"**[{dup['index2']}]** {dup['title2']}\n\n"
            md += "---\n\n"

        # Recommendations
        md += "## Recommendations (SOP v4.0)\n\n"
        if report.get('placeholder_doi_count', 0) > 0:
            md += f"1. **CRITICAL:** Replace {report['placeholder_doi_count']} placeholder DOI(s) with real DOIs or mark as UNKNOWN\n"
        if report['invalid_doi_count'] > 0:
            md += f"2. Fix or replace {report['invalid_doi_count']} invalid DOI(s)\n"
        if report['no_doi_count'] > 0:
            md += f"3. Add DOIs for {report['no_doi_count']} reference(s) without DOI\n"
        if report.get('invalid_url_count', 0) > 0:
            md += f"4. Fix or verify {report['invalid_url_count']} inaccessible URL(s)\n"
        if report['duplicate_count'] > 0:
            md += f"5. Remove {report['duplicate_count']} duplicate reference(s)\n"
        if report['total_count'] < 20:
            md += f"6. Add {20 - report['total_count']} more reference(s) to reach minimum of 20\n"

        if gate_pass:
            md += "\n✅ All checks passed! Ready to proceed to next step.\n"
        else:
            md += "\n❌ Gate 1.6 FAILED. Please fix the issues above before proceeding.\n"

        return md
