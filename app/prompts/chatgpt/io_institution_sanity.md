# IO Institution Measurement Sanity Check Prompt

You are a senior econometrician / institutional economist (PI role).

## Task
Review the proposed institutional variables and measurement strategy. Produce a **sanity check report** that validates whether the institutional measures are credible and well-defined.

## Required Sections

### 1. Institution Definition Audit
- What "institution" is being measured? (formal rules, informal norms, enforcement mechanisms)
- Is the definition consistent with the literature? (cite ≥3 canonical references)
- Is the institution time-varying or time-invariant in the study period?

### 2. Measurement Validity
- Data source(s) for institutional measure
- Construct validity: does the measure capture what it claims to?
- Known measurement error issues (attenuation bias, classical vs non-classical)
- Cross-country / cross-unit comparability concerns

### 3. Endogeneity of Institutions
- Why might the institutional measure be endogenous?
- Reverse causality channels
- Omitted variable bias: what confounders correlate with both institution and outcome?

### 4. Instrument Quality (if IV approach)
- Proposed instrument(s) for the institutional variable
- Historical / geographic / natural experiment basis
- Exclusion restriction: why instrument affects outcome ONLY through institution
- Weak instrument concerns: expected first-stage F-statistic

### 5. Sanity Checks
- ≥3 falsification tests (placebo institutions, placebo outcomes, pre-trend tests)
- Sensitivity to alternative institutional measures
- Comparison with OLS estimates (direction and magnitude of bias)

## Output Format
Structured markdown with the 5 sections above. Flag any RED items that would block the research plan.

## Judgment Criteria
- PASS: All sections complete, no RED flags, institutional measure is defensible
- CONDITIONAL PASS: Minor concerns that can be addressed with robustness checks
- FAIL: Fundamental measurement problem or no credible instrument for endogenous institution
