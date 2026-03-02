"""
Consistency Linter Service (v4.0)
Cross-document consistency checking for research projects
"""
import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
from fuzzywuzzy import fuzz
from collections import defaultdict

logger = logging.getLogger(__name__)


class ConsistencyLinter:
    """Cross-document consistency checker"""

    def __init__(self, threshold: float = 0.8):
        """
        Initialize Consistency Linter

        Args:
            threshold: Consistency check threshold (0-1, default 0.8)
        """
        self.threshold = threshold

    def extract_claims(self, claims_content: str) -> List[Dict[str, Any]]:
        """
        Extract claims from Claims and NonClaims document

        Args:
            claims_content: Content of Claims and NonClaims document

        Returns:
            List of claim dicts with id, text, type (claim/non-claim)
        """
        claims = []

        # Pattern to match numbered claims
        claim_pattern = re.compile(r'(?:^|\n)(?:Claim\s+)?(\d+)[.:\)]\s*(.+?)(?=\n(?:Claim\s+)?\d+[.:\)]|\n\n|$)', re.IGNORECASE | re.DOTALL)

        # Try to find claims section
        claims_section_match = re.search(r'##?\s*Claims?\s*\n(.*?)(?=##?\s*Non-?Claims?|$)', claims_content, re.IGNORECASE | re.DOTALL)
        if claims_section_match:
            claims_text = claims_section_match.group(1)
            for match in claim_pattern.finditer(claims_text):
                claim_id = match.group(1)
                claim_text = match.group(2).strip()
                claims.append({
                    'id': f"claim_{claim_id}",
                    'text': claim_text,
                    'type': 'claim'
                })

        # Try to find non-claims section
        nonclaims_section_match = re.search(r'##?\s*Non-?Claims?\s*\n(.*?)(?=##|$)', claims_content, re.IGNORECASE | re.DOTALL)
        if nonclaims_section_match:
            nonclaims_text = nonclaims_section_match.group(1)
            for match in claim_pattern.finditer(nonclaims_text):
                claim_id = match.group(1)
                claim_text = match.group(2).strip()
                claims.append({
                    'id': f"nonclaim_{claim_id}",
                    'text': claim_text,
                    'type': 'non-claim'
                })

        logger.info(f"Extracted {len(claims)} claims/non-claims")
        return claims

    def extract_figures_tables(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract figure/table references from document

        Args:
            content: Document content

        Returns:
            List of figure/table dicts with id, type, context
        """
        figures_tables = []

        # Pattern to match figure/table references
        fig_pattern = re.compile(r'(?:Figure|Fig\.?)\s*(\d+)', re.IGNORECASE)
        table_pattern = re.compile(r'Table\s*(\d+)', re.IGNORECASE)

        # Find all figure references
        for match in fig_pattern.finditer(content):
            fig_id = match.group(1)
            # Get surrounding context (50 chars before and after)
            start = max(0, match.start() - 50)
            end = min(len(content), match.end() + 50)
            context = content[start:end]

            figures_tables.append({
                'id': f"fig_{fig_id}",
                'type': 'figure',
                'context': context.strip()
            })

        # Find all table references
        for match in table_pattern.finditer(content):
            table_id = match.group(1)
            start = max(0, match.start() - 50)
            end = min(len(content), match.end() + 50)
            context = content[start:end]

            figures_tables.append({
                'id': f"table_{table_id}",
                'type': 'table',
                'context': context.strip()
            })

        logger.info(f"Extracted {len(figures_tables)} figure/table references")
        return figures_tables

    def map_claims_to_evidence(self, claims: List[Dict[str, Any]],
                               proposal_content: str,
                               figure_table_list_content: str = "") -> Dict[str, Any]:
        """
        Map claims to supporting evidence (figures/tables/tests)

        Args:
            claims: List of claim dicts
            proposal_content: Full Proposal content
            figure_table_list_content: Figure/Table List content (optional)

        Returns:
            Dict with mapping results and validation
        """
        logger.info("Mapping claims to evidence...")

        mapping = {
            'claim_to_evidence': {},
            'unmapped_claims': [],
            'evidence_without_claims': [],
            'mapping_score': 0.0
        }

        # Extract figures/tables from proposal
        evidence_items = self.extract_figures_tables(proposal_content)

        # If Figure/Table List is available, also extract from there
        if figure_table_list_content:
            evidence_items.extend(self.extract_figures_tables(figure_table_list_content))

        # Remove duplicates
        evidence_ids = set()
        unique_evidence = []
        for item in evidence_items:
            if item['id'] not in evidence_ids:
                evidence_ids.add(item['id'])
                unique_evidence.append(item)

        evidence_items = unique_evidence

        # Map each claim to evidence
        for claim in claims:
            if claim['type'] != 'claim':  # Only map actual claims, not non-claims
                continue

            claim_id = claim['id']
            claim_text = claim['text'].lower()

            # Find evidence that mentions this claim
            supporting_evidence = []

            for evidence in evidence_items:
                # Check if claim keywords appear near evidence reference
                # Simple heuristic: check if claim number appears near figure/table reference
                claim_num = claim_id.split('_')[1]
                if f"claim {claim_num}" in evidence['context'].lower() or \
                   f"claim{claim_num}" in evidence['context'].lower():
                    supporting_evidence.append(evidence['id'])

            mapping['claim_to_evidence'][claim_id] = supporting_evidence

            if not supporting_evidence:
                mapping['unmapped_claims'].append(claim_id)

        # Find evidence not mapped to any claim
        mapped_evidence = set()
        for evidence_list in mapping['claim_to_evidence'].values():
            mapped_evidence.update(evidence_list)

        for evidence in evidence_items:
            if evidence['id'] not in mapped_evidence:
                mapping['evidence_without_claims'].append(evidence['id'])

        # Calculate mapping score
        total_claims = len([c for c in claims if c['type'] == 'claim'])
        if total_claims > 0:
            mapped_claims = total_claims - len(mapping['unmapped_claims'])
            mapping['mapping_score'] = mapped_claims / total_claims
        else:
            mapping['mapping_score'] = 0.0

        logger.info(f"Mapping score: {mapping['mapping_score']:.2f}")
        return mapping

    def check_keyword_consistency(self, intake_keywords: List[str],
                                  documents: Dict[str, str]) -> Dict[str, Any]:
        """
        Check keyword consistency across documents

        Args:
            intake_keywords: Keywords from Project Intake Card
            documents: Dict of {doc_name: content}

        Returns:
            Dict with consistency results
        """
        logger.info("Checking keyword consistency...")

        results = {
            'keyword_presence': {},
            'missing_keywords': defaultdict(list),
            'consistency_score': 0.0
        }

        # Normalize keywords
        normalized_keywords = [kw.lower().strip() for kw in intake_keywords]

        # Check each document
        for doc_name, content in documents.items():
            content_lower = content.lower()
            present_keywords = []
            missing_keywords = []

            for keyword in normalized_keywords:
                # Check if keyword appears in document
                if keyword in content_lower:
                    present_keywords.append(keyword)
                else:
                    missing_keywords.append(keyword)

            results['keyword_presence'][doc_name] = {
                'present': present_keywords,
                'missing': missing_keywords,
                'coverage': len(present_keywords) / len(normalized_keywords) if normalized_keywords else 0.0
            }

            if missing_keywords:
                results['missing_keywords'][doc_name] = missing_keywords

        # Calculate overall consistency score
        if documents:
            total_coverage = sum(info['coverage'] for info in results['keyword_presence'].values())
            results['consistency_score'] = total_coverage / len(documents)
        else:
            results['consistency_score'] = 0.0

        logger.info(f"Keyword consistency score: {results['consistency_score']:.2f}")
        return results

    def check_constraint_propagation(self, intake_constraints: List[str],
                                    documents: Dict[str, str]) -> Dict[str, Any]:
        """
        Check if hard constraints from Intake Card are propagated to all documents

        Args:
            intake_constraints: Hard constraints from Project Intake Card
            documents: Dict of {doc_name: content}

        Returns:
            Dict with constraint propagation results
        """
        logger.info("Checking constraint propagation...")

        results = {
            'constraint_mentions': {},
            'missing_constraints': defaultdict(list),
            'propagation_score': 0.0
        }

        # Check each document
        for doc_name, content in documents.items():
            content_lower = content.lower()
            mentioned_constraints = []
            missing_constraints = []

            for constraint in intake_constraints:
                constraint_lower = constraint.lower()
                # Use fuzzy matching for constraint detection
                # Check if any sentence in document has high similarity to constraint
                sentences = re.split(r'[.!?]\s+', content)
                max_similarity = 0.0

                for sentence in sentences:
                    similarity = fuzz.partial_ratio(constraint_lower, sentence.lower()) / 100.0
                    max_similarity = max(max_similarity, similarity)

                if max_similarity >= self.threshold:
                    mentioned_constraints.append(constraint)
                else:
                    missing_constraints.append(constraint)

            results['constraint_mentions'][doc_name] = {
                'mentioned': mentioned_constraints,
                'missing': missing_constraints,
                'coverage': len(mentioned_constraints) / len(intake_constraints) if intake_constraints else 0.0
            }

            if missing_constraints:
                results['missing_constraints'][doc_name] = missing_constraints

        # Calculate overall propagation score
        if documents:
            total_coverage = sum(info['coverage'] for info in results['constraint_mentions'].values())
            results['propagation_score'] = total_coverage / len(documents)
        else:
            results['propagation_score'] = 0.0

        logger.info(f"Constraint propagation score: {results['propagation_score']:.2f}")
        return results

    def check_hard_reject_consistency(self, intake_hard_rejects: List[str],
                                     plan_freeze_content: str,
                                     engineering_spec_content: str) -> Dict[str, Any]:
        """
        Check if hard rejects from Intake Card are properly excluded (SOP v4.0 Section 8.2)

        SOP Requirement:
        "Plan Freeze 禁止 hard reject X，但 Engineering Spec 里出现 hard reject → fail"

        Args:
            intake_hard_rejects: Hard reject items from Project Intake Card
            plan_freeze_content: Research Plan FROZEN document content
            engineering_spec_content: Engineering Spec document content

        Returns:
            Dict with hard reject consistency results
        """
        logger.info("Checking hard reject consistency...")

        results = {
            'hard_rejects_in_plan': [],
            'hard_rejects_in_spec': [],
            'violations': [],
            'consistency_score': 1.0
        }

        if not intake_hard_rejects:
            logger.info("No hard rejects defined in Intake Card")
            return results

        # Check Plan Freeze document
        plan_lower = plan_freeze_content.lower()
        for hard_reject in intake_hard_rejects:
            hard_reject_lower = hard_reject.lower()

            # Use fuzzy matching to detect mentions
            sentences = re.split(r'[.!?]\s+', plan_freeze_content)
            max_similarity = 0.0
            matching_sentence = None

            for sentence in sentences:
                similarity = fuzz.partial_ratio(hard_reject_lower, sentence.lower()) / 100.0
                if similarity > max_similarity:
                    max_similarity = similarity
                    matching_sentence = sentence

            # If hard reject is mentioned with high similarity, it's a violation
            if max_similarity >= self.threshold:
                results['hard_rejects_in_plan'].append({
                    'hard_reject': hard_reject,
                    'similarity': max_similarity,
                    'context': matching_sentence[:200] if matching_sentence else ''
                })
                results['violations'].append({
                    'type': 'hard_reject_in_plan',
                    'severity': 'high',
                    'hard_reject': hard_reject,
                    'document': 'Research Plan FROZEN',
                    'message': f"Hard reject '{hard_reject}' found in Plan Freeze (should be excluded)"
                })

        # Check Engineering Spec document
        spec_lower = engineering_spec_content.lower()
        for hard_reject in intake_hard_rejects:
            hard_reject_lower = hard_reject.lower()

            # Use fuzzy matching to detect mentions
            sentences = re.split(r'[.!?]\s+', engineering_spec_content)
            max_similarity = 0.0
            matching_sentence = None

            for sentence in sentences:
                similarity = fuzz.partial_ratio(hard_reject_lower, sentence.lower()) / 100.0
                if similarity > max_similarity:
                    max_similarity = similarity
                    matching_sentence = sentence

            # If hard reject is mentioned with high similarity, it's a violation
            if max_similarity >= self.threshold:
                results['hard_rejects_in_spec'].append({
                    'hard_reject': hard_reject,
                    'similarity': max_similarity,
                    'context': matching_sentence[:200] if matching_sentence else ''
                })
                results['violations'].append({
                    'type': 'hard_reject_in_spec',
                    'severity': 'critical',
                    'hard_reject': hard_reject,
                    'document': 'Engineering Spec',
                    'message': f"Hard reject '{hard_reject}' found in Engineering Spec (CRITICAL violation)"
                })

        # Calculate consistency score
        total_violations = len(results['hard_rejects_in_plan']) + len(results['hard_rejects_in_spec'])
        if intake_hard_rejects:
            results['consistency_score'] = 1.0 - (total_violations / (len(intake_hard_rejects) * 2))
            results['consistency_score'] = max(0.0, results['consistency_score'])
        else:
            results['consistency_score'] = 1.0

        logger.info(f"Hard reject consistency score: {results['consistency_score']:.2f}, "
                   f"violations: {total_violations}")
        return results

    def run_full_check(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run full consistency check on project

        Args:
            project_data: Dict containing all project documents and metadata

        Returns:
            Dict with comprehensive consistency report
        """
        logger.info("Running full consistency check...")
        start_time = datetime.now()

        report = {
            'timestamp': start_time.isoformat(),
            'claim_to_evidence': {},
            'keyword_consistency': {},
            'constraint_propagation': {},
            'overall_score': 0.0,
            'issues': [],
            'recommendations': []
        }

        # 1. Claim-to-Evidence Mapping
        if 'claims_content' in project_data and 'proposal_content' in project_data:
            claims = self.extract_claims(project_data['claims_content'])
            mapping = self.map_claims_to_evidence(
                claims,
                project_data['proposal_content'],
                project_data.get('figure_table_list_content', '')
            )
            report['claim_to_evidence'] = mapping

            # Add issues
            if mapping['unmapped_claims']:
                report['issues'].append({
                    'type': 'unmapped_claims',
                    'severity': 'high',
                    'count': len(mapping['unmapped_claims']),
                    'details': mapping['unmapped_claims']
                })
                report['recommendations'].append(
                    f"Map {len(mapping['unmapped_claims'])} unmapped claim(s) to specific figures/tables/tests"
                )

        # 2. Keyword Consistency
        if 'intake_keywords' in project_data and 'documents' in project_data:
            keyword_check = self.check_keyword_consistency(
                project_data['intake_keywords'],
                project_data['documents']
            )
            report['keyword_consistency'] = keyword_check

            # Add issues
            for doc_name, missing_kws in keyword_check['missing_keywords'].items():
                if missing_kws:
                    report['issues'].append({
                        'type': 'missing_keywords',
                        'severity': 'medium',
                        'document': doc_name,
                        'keywords': missing_kws
                    })

            if keyword_check['consistency_score'] < self.threshold:
                report['recommendations'].append(
                    f"Improve keyword consistency (current: {keyword_check['consistency_score']:.2f}, target: {self.threshold})"
                )

        # 3. Constraint Propagation
        if 'intake_constraints' in project_data and 'documents' in project_data:
            constraint_check = self.check_constraint_propagation(
                project_data['intake_constraints'],
                project_data['documents']
            )
            report['constraint_propagation'] = constraint_check

            # Add issues
            for doc_name, missing_constraints in constraint_check['missing_constraints'].items():
                if missing_constraints:
                    report['issues'].append({
                        'type': 'missing_constraints',
                        'severity': 'high',
                        'document': doc_name,
                        'constraints': missing_constraints
                    })

            if constraint_check['propagation_score'] < self.threshold:
                report['recommendations'].append(
                    f"Ensure hard constraints are mentioned in all key documents (current: {constraint_check['propagation_score']:.2f}, target: {self.threshold})"
                )

        # 4. Hard Reject Consistency (SOP v4.0 Section 8.2)
        if ('intake_hard_rejects' in project_data and
            'plan_freeze_content' in project_data and
            'engineering_spec_content' in project_data):
            hard_reject_check = self.check_hard_reject_consistency(
                project_data['intake_hard_rejects'],
                project_data['plan_freeze_content'],
                project_data['engineering_spec_content']
            )
            report['hard_reject_consistency'] = hard_reject_check

            # Add violations as issues
            for violation in hard_reject_check['violations']:
                report['issues'].append(violation)

            # Add recommendations
            if hard_reject_check['violations']:
                if any(v['severity'] == 'critical' for v in hard_reject_check['violations']):
                    report['recommendations'].append(
                        f"CRITICAL: Remove {len([v for v in hard_reject_check['violations'] if v['severity'] == 'critical'])} hard reject(s) from Engineering Spec"
                    )
                if any(v['severity'] == 'high' for v in hard_reject_check['violations']):
                    report['recommendations'].append(
                        f"Remove {len([v for v in hard_reject_check['violations'] if v['severity'] == 'high'])} hard reject(s) from Plan Freeze"
                    )

        # Calculate overall score
        scores = []
        if 'claim_to_evidence' in report and 'mapping_score' in report['claim_to_evidence']:
            scores.append(report['claim_to_evidence']['mapping_score'])
        if 'keyword_consistency' in report and 'consistency_score' in report['keyword_consistency']:
            scores.append(report['keyword_consistency']['consistency_score'])
        if 'constraint_propagation' in report and 'propagation_score' in report['constraint_propagation']:
            scores.append(report['constraint_propagation']['propagation_score'])
        if 'hard_reject_consistency' in report and 'consistency_score' in report['hard_reject_consistency']:
            scores.append(report['hard_reject_consistency']['consistency_score'])

        if scores:
            report['overall_score'] = sum(scores) / len(scores)
        else:
            report['overall_score'] = 0.0

        # Performance check
        duration = (datetime.now() - start_time).total_seconds()
        report['duration_seconds'] = duration

        if duration > 2.0:
            logger.warning(f"Consistency check took {duration:.2f}s (target: <2s)")
        else:
            logger.info(f"Consistency check completed in {duration:.2f}s")

        return report

    def generate_report(self, check_results: Dict[str, Any]) -> str:
        """
        Generate Markdown consistency report

        Args:
            check_results: Results from run_full_check()

        Returns:
            str: Markdown report
        """
        md = f"""# Consistency Check Report

**Generated:** {check_results['timestamp']}
**Duration:** {check_results.get('duration_seconds', 0):.2f}s
**Overall Score:** {check_results['overall_score']:.2f}

---

## Summary

| Check | Score | Status |
|-------|-------|--------|
"""

        # Claim-to-Evidence
        if 'claim_to_evidence' in check_results:
            score = check_results['claim_to_evidence'].get('mapping_score', 0.0)
            status = "✅ PASS" if score >= self.threshold else "❌ FAIL"
            md += f"| Claim-to-Evidence Mapping | {score:.2f} | {status} |\n"

        # Keyword Consistency
        if 'keyword_consistency' in check_results:
            score = check_results['keyword_consistency'].get('consistency_score', 0.0)
            status = "✅ PASS" if score >= self.threshold else "❌ FAIL"
            md += f"| Keyword Consistency | {score:.2f} | {status} |\n"

        # Constraint Propagation
        if 'constraint_propagation' in check_results:
            score = check_results['constraint_propagation'].get('propagation_score', 0.0)
            status = "✅ PASS" if score >= self.threshold else "❌ FAIL"
            md += f"| Constraint Propagation | {score:.2f} | {status} |\n"

        # Hard Reject Consistency (SOP v4.0)
        if 'hard_reject_consistency' in check_results:
            score = check_results['hard_reject_consistency'].get('consistency_score', 1.0)
            status = "✅ PASS" if score >= self.threshold else "❌ FAIL"
            md += f"| Hard Reject Consistency | {score:.2f} | {status} |\n"

        md += "\n---\n\n"

        # Issues
        if check_results.get('issues'):
            md += "## Issues Found\n\n"
            for i, issue in enumerate(check_results['issues'], 1):
                # Determine severity emoji
                if issue['severity'] == 'critical':
                    severity_emoji = "🔴🔴"
                elif issue['severity'] == 'high':
                    severity_emoji = "🔴"
                else:
                    severity_emoji = "🟡"

                md += f"### {i}. {severity_emoji} {issue['type'].replace('_', ' ').title()}\n\n"
                md += f"**Severity:** {issue['severity']}\n\n"

                if 'document' in issue:
                    md += f"**Document:** {issue['document']}\n\n"

                if 'message' in issue:
                    md += f"**Message:** {issue['message']}\n\n"

                if 'details' in issue:
                    md += f"**Details:** {', '.join(issue['details'])}\n\n"
                elif 'keywords' in issue:
                    md += f"**Missing Keywords:** {', '.join(issue['keywords'])}\n\n"
                elif 'constraints' in issue:
                    md += f"**Missing Constraints:**\n"
                    for constraint in issue['constraints']:
                        md += f"- {constraint}\n"
                    md += "\n"

            md += "---\n\n"

        # Recommendations
        if check_results.get('recommendations'):
            md += "## Recommendations\n\n"
            for i, rec in enumerate(check_results['recommendations'], 1):
                md += f"{i}. {rec}\n"
            md += "\n---\n\n"

        # Detailed Results
        md += "## Detailed Results\n\n"

        # Claim-to-Evidence Details
        if 'claim_to_evidence' in check_results:
            mapping = check_results['claim_to_evidence']
            md += "### Claim-to-Evidence Mapping\n\n"
            md += f"- **Mapping Score:** {mapping.get('mapping_score', 0.0):.2f}\n"
            md += f"- **Unmapped Claims:** {len(mapping.get('unmapped_claims', []))}\n"
            md += f"- **Evidence Without Claims:** {len(mapping.get('evidence_without_claims', []))}\n\n"

            if mapping.get('unmapped_claims'):
                md += "**Unmapped Claims:**\n"
                for claim_id in mapping['unmapped_claims']:
                    md += f"- {claim_id}\n"
                md += "\n"

        # Keyword Consistency Details
        if 'keyword_consistency' in check_results:
            kw_check = check_results['keyword_consistency']
            md += "### Keyword Consistency\n\n"
            md += f"- **Overall Score:** {kw_check.get('consistency_score', 0.0):.2f}\n\n"

            if kw_check.get('keyword_presence'):
                md += "**Per-Document Coverage:**\n\n"
                for doc_name, info in kw_check['keyword_presence'].items():
                    md += f"- **{doc_name}:** {info['coverage']:.2f} ({len(info['present'])}/{len(info['present']) + len(info['missing'])} keywords)\n"
                md += "\n"

        # Constraint Propagation Details
        if 'constraint_propagation' in check_results:
            constraint_check = check_results['constraint_propagation']
            md += "### Constraint Propagation\n\n"
            md += f"- **Overall Score:** {constraint_check.get('propagation_score', 0.0):.2f}\n\n"

            if constraint_check.get('constraint_mentions'):
                md += "**Per-Document Coverage:**\n\n"
                for doc_name, info in constraint_check['constraint_mentions'].items():
                    md += f"- **{doc_name}:** {info['coverage']:.2f} ({len(info['mentioned'])}/{len(info['mentioned']) + len(info['missing'])} constraints)\n"
                md += "\n"

        # Hard Reject Consistency Details (SOP v4.0)
        if 'hard_reject_consistency' in check_results:
            hr_check = check_results['hard_reject_consistency']
            md += "### Hard Reject Consistency (SOP v4.0 Section 8.2)\n\n"
            md += f"- **Consistency Score:** {hr_check.get('consistency_score', 1.0):.2f}\n"
            md += f"- **Violations:** {len(hr_check.get('violations', []))}\n\n"

            if hr_check.get('hard_rejects_in_plan'):
                md += "**⚠️ Hard Rejects Found in Plan Freeze:**\n\n"
                for item in hr_check['hard_rejects_in_plan']:
                    md += f"- **{item['hard_reject']}** (similarity: {item['similarity']:.2f})\n"
                    if item.get('context'):
                        md += f"  - Context: \"{item['context']}...\"\n"
                md += "\n"

            if hr_check.get('hard_rejects_in_spec'):
                md += "**🔴 CRITICAL: Hard Rejects Found in Engineering Spec:**\n\n"
                for item in hr_check['hard_rejects_in_spec']:
                    md += f"- **{item['hard_reject']}** (similarity: {item['similarity']:.2f})\n"
                    if item.get('context'):
                        md += f"  - Context: \"{item['context']}...\"\n"
                md += "\n"

            if not hr_check.get('violations'):
                md += "✅ No hard reject violations found.\n\n"

        return md
