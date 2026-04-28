# Phase 2: Tax Engine & Statutory Filing

> Quarterly TDS deadlines are non-negotiable. Form 24Q due every quarter,
> Form 16 due annually. New Form 138/130 replaces them from FY 2026-27.
> This phase makes filing a one-click operation.

---

## 1. Architecture

```
hrms_enhanced/tax/
├── engine.py                    # TDS computation orchestrator
├── regime.py                    # Old vs New regime logic + employee declaration
├── section192.py                # Salary TDS calculation (detailed)
├── declarations/
│   ├── form_12bb.py             # Investment declaration workflow
│   ├── proof_submission.py      # Proof upload + verification
│   └── hra_exemption.py         # HRA exemption calculation
├── forms/
│   ├── form_24q.py              # Quarterly TDS return generation
│   ├── form_16.py               # Annual TDS certificate generation
│   ├── form_138.py              # New quarterly return (replaces 24Q from July 2026)
│   ├── form_130.py              # New annual certificate (replaces Form 16)
│   └── challan_281.py           # TDS deposit challan
├── reconciliation.py            # TDS variance detection + reconciliation
└── projections.py               # Annual tax projection per employee
```

---

## 2. New Doctypes

### 2.1 Tax Regime Declaration

Employees must declare their tax regime at start of FY. System enforces this.

```
Tax Regime Declaration
├── employee: Link → Employee (required)
├── financial_year: Link → Fiscal Year (required)
├── regime: Select [Old Regime, New Regime] (required)
├── declared_on: Date (auto: creation date)
├── previous_regime: Data (read-only, fetched from last FY)
├── reason_for_change: Small Text (required if different from previous)
├── status: Select [Active, Superseded, Cancelled]
│
├── Section: Old Regime Declarations (visible only if regime = Old)
│   ├── child: Tax Declaration Item
│   │   ├── section: Select [80C, 80D, 80E, 80G, 80TTA, 80U, 24b, HRA, LTA, Other]
│   │   ├── sub_category: Data (e.g., "PPF", "ELSS", "Life Insurance")
│   │   ├── declared_amount: Currency
│   │   ├── proof_submitted: Check
│   │   ├── verified_amount: Currency
│   │   ├── verified_by: Link → User
│   │   └── attachment: Attach
│   │
│   ├── total_80c: Currency (auto-calculated, capped at 1,50,000)
│   ├── total_80d: Currency (auto-calculated)
│   ├── total_deductions: Currency (auto-calculated)
│   └── hra_annual_exemption: Currency (auto from HRA calculator)
│
├── Section: Tax Computation Preview
│   ├── estimated_annual_income: Currency (auto from salary structure)
│   ├── estimated_deductions: Currency (auto from declarations)
│   ├── estimated_taxable_income: Currency
│   ├── estimated_annual_tax: Currency
│   └── estimated_monthly_tds: Currency
│
└── Unique: (employee, financial_year) — one active declaration per FY
```

### 2.2 TDS Computation Sheet

Auto-generated monthly — the working paper behind each employee's TDS.

```
TDS Computation Sheet
├── employee: Link → Employee
├── financial_year: Link → Fiscal Year
├── month: Int (1-12)
├── salary_slip: Link → Salary Slip
│
├── Section: Income
│   ├── gross_salary_ytd: Currency
│   ├── projected_gross_annual: Currency
│   ├── hra_received_ytd: Currency
│   ├── hra_exemption_ytd: Currency
│   ├── standard_deduction: Currency (75,000 new / 50,000 old)
│   ├── professional_tax_ytd: Currency
│   ├── other_income_declared: Currency
│   └── net_taxable_salary: Currency
│
├── Section: Deductions (Old Regime only)
│   ├── section_80c: Currency (capped 1,50,000)
│   ├── section_80d: Currency
│   ├── section_80e: Currency
│   ├── section_24b: Currency (home loan interest, capped 2,00,000)
│   ├── section_80ccd_1b: Currency (NPS additional, capped 50,000)
│   ├── section_80ccd_2: Currency (employer NPS, up to 14% of salary)
│   ├── other_deductions: Currency
│   └── total_deductions: Currency
│
├── Section: Tax Computation
│   ├── taxable_income: Currency
│   ├── tax_on_income: Currency
│   ├── surcharge: Currency (if income > 50L)
│   ├── health_cess: Currency (4%)
│   ├── total_tax_liability: Currency
│   ├── relief_87a: Currency (rebate if taxable income ≤ threshold)
│   ├── marginal_relief: Currency (if applicable)
│   ├── net_tax_payable: Currency
│   ├── tds_deducted_ytd: Currency
│   ├── tds_this_month: Currency
│   └── balance_tax_remaining: Currency
│
└── auto-generated, not editable — serves as audit trail
```

### 2.3 Investment Proof Submission

Window-based: HR opens a submission window, employees upload proofs.

```
Investment Proof Window
├── financial_year: Link → Fiscal Year
├── company: Link → Company
├── open_date: Date
├── close_date: Date
├── status: Select [Draft, Open, Closed, Verified]
├── reminder_sent: Check
│
├── child: Proof Submission Entry
│   ├── employee: Link → Employee
│   ├── declaration: Link → Tax Regime Declaration
│   ├── submission_date: Datetime
│   ├── status: Select [Submitted, Under Review, Verified, Rejected]
│   ├── verified_by: Link → User
│   └── notes: Small Text
│
└── On Close: trigger TDS recomputation for all employees with verified proofs
```

---

## 3. TDS Calculation Engine

### 3.1 Core TDS Flow

```
Monthly Payroll Run
│
├── 1. Get employee's active Tax Regime Declaration
│     └── If missing → block payroll + create Compliance Alert
│
├── 2. Project annual income
│     ├── Gross salary × 12 (or proportional if mid-year joiner)
│     ├── + variable pay / bonus (if declared)
│     ├── + other income (declared by employee)
│     └── = Projected Annual Gross Income
│
├── 3. Calculate exemptions
│     ├── HRA exemption (min of: actual HRA, 50%/40% of basic, rent - 10% basic)
│     ├── Standard deduction (Rs 75,000 new / Rs 50,000 old)
│     ├── Professional tax (actual deducted)
│     └── = Net Taxable Salary
│
├── 4. Apply deductions (Old Regime only)
│     ├── 80C: up to Rs 1,50,000 (proof-verified amount after window closes)
│     ├── 80D: medical insurance (25K self, 50K parents 60+)
│     ├── 80E: education loan interest
│     ├── 24(b): home loan interest (up to 2,00,000)
│     ├── 80CCD(1B): NPS (up to 50,000)
│     ├── 80CCD(2): employer NPS (up to 14% of salary)
│     └── = Taxable Income
│
├── 5. Compute tax
│     ├── Apply applicable slab (Old or New regime)
│     ├── + Surcharge (10% if >50L, 15% if >1Cr, 25% if >2Cr)
│     ├── + Health & Education Cess (4%)
│     ├── − Rebate 87A (new regime: nil tax if income ≤ Rs 12,00,000 with
│     │     marginal relief up to Rs 12,75,000)
│     ├── − Marginal relief (if applicable at surcharge thresholds)
│     └── = Net Annual Tax
│
├── 6. Calculate monthly TDS
│     ├── net_annual_tax − tds_already_deducted_ytd
│     ├── ÷ remaining_months_in_fy
│     └── = TDS for this month
│
└── 7. Create TDS Computation Sheet (audit trail)
```

### 3.2 New Regime Slabs (FY 2025-26 onwards)

```python
NEW_REGIME_SLABS = [
    (0,        400000,  0),
    (400001,   800000,  5),
    (800001,  1200000, 10),
    (1200001, 1600000, 15),
    (1600001, 2000000, 20),
    (2000001, 2400000, 25),
    (2400001, float('inf'), 30),
]
# Standard deduction: Rs 75,000
# Rebate 87A: Nil tax if taxable income ≤ Rs 12,00,000
# Marginal relief: if income between 12,00,000 and 12,75,000
```

### 3.3 Old Regime Slabs (FY 2025-26)

```python
OLD_REGIME_SLABS = [
    (0,        250000,  0),
    (250001,   500000,  5),
    (500001,  1000000, 20),
    (1000001, float('inf'), 30),
]
# Standard deduction: Rs 50,000
# All Section 80 deductions applicable
# HRA exemption applicable
```

### 3.4 HRA Exemption Calculator

```python
def calculate_hra_exemption(employee, financial_year):
    """
    HRA exemption = minimum of:
    1. Actual HRA received
    2. 50% of basic (metro) or 40% of basic (non-metro)
    3. Rent paid − 10% of basic salary

    Metro cities: Delhi, Mumbai, Kolkata, Chennai
    """
    declaration = get_tax_declaration(employee, financial_year)
    salary_structure = get_salary_structure(employee)

    annual_basic = salary_structure.basic * 12
    annual_hra = salary_structure.hra * 12
    annual_rent = declaration.annual_rent_paid or 0

    if annual_rent == 0:
        return 0

    metro = is_metro_city(employee)
    metro_percent = 50 if metro else 40

    exemption = min(
        annual_hra,
        annual_basic * metro_percent / 100,
        max(0, annual_rent - (annual_basic * 10 / 100)),
    )

    return round(exemption, 0)
```

---

## 4. Form Generation

### 4.1 Form 24Q (Quarterly TDS Return)

```
Generation Flow:
│
├── Input: Quarter (Q1/Q2/Q3/Q4), Financial Year, Company
│
├── Annexure I (all quarters):
│   ├── Challan details (BSR code, date, challan serial, amount)
│   ├── Deductee details per challan:
│   │   ├── Employee PAN
│   │   ├── Employee name
│   │   ├── Section code (192)
│   │   ├── Amount paid/credited
│   │   ├── TDS deducted
│   │   ├── TDS deposited
│   │   ├── Date of deduction
│   │   └── Date of deposit
│   └── Total: matches challan amount
│
├── Annexure II (Q4 only — full year salary statement):
│   ├── For each employee:
│   │   ├── PAN, name, designation, address
│   │   ├── Gross salary (breakup: basic, HRA, allowances, perquisites)
│   │   ├── Exemptions claimed (HRA, LTA, etc.)
│   │   ├── Standard deduction
│   │   ├── Income from other sources
│   │   ├── 80C/80D/80E deductions (with sub-breakup)
│   │   ├── Taxable income
│   │   ├── Tax computed
│   │   ├── Rebate 87A
│   │   ├── Surcharge + cess
│   │   ├── Total tax
│   │   ├── TDS deducted each month (12 columns)
│   │   └── Total TDS for year
│   └── Summary: total salary paid, total tax deducted, total tax deposited
│
├── Output: Text file in NSDL/TIN prescribed format (.txt)
│   └── Upload-ready for TIN-NSDL portal / Traces
│
└── Create Compliance Filing Log entry
```

### 4.2 Form 16 (Annual TDS Certificate)

```
Generation Flow:
│
├── Input: Financial Year, Company, Employee (optional — all if blank)
│
├── Part A (auto from Form 24Q data):
│   ├── Employer TAN, PAN, name, address
│   ├── Employee PAN, name, address, designation
│   ├── Assessment year
│   ├── Quarter-wise: TDS deducted, TDS deposited, challan details
│   └── Verification: signed by employer
│
├── Part B (from TDS Computation Sheets):
│   ├── Gross salary breakup
│   ├── Exemptions: HRA, LTA, standard deduction
│   ├── Net salary
│   ├── Income from other sources (as declared)
│   ├── Gross total income
│   ├── Deductions under Chapter VI-A (80C, 80D, etc.)
│   ├── Taxable income
│   ├── Tax on total income
│   ├── Rebate under Section 87A
│   ├── Surcharge + H&E Cess
│   ├── Tax payable
│   ├── Relief under Section 89 (if applicable)
│   ├── Net tax payable
│   └── TDS deducted: monthly breakup
│
├── Output: PDF per employee (print-ready)
│   └── Bulk download as ZIP
│
└── Employee self-service: download own Form 16 from portal
```

### 4.3 Form 138 (New — Replaces Form 24Q from July 2026)

```
Key differences from Form 24Q:
├── First filing: July 2026 for April-June 2026 salaries
├── More granular salary breakup required
├── Additional fields for perquisites valuation
├── Regime-wise reporting (old vs new per employee)
└── Digital signature mandatory

Implementation:
├── Track both formats: generate 24Q for pre-July 2026, 138 for post
├── Migration helper: auto-maps 24Q fields to 138 fields
└── Validation: ensures all new mandatory fields are populated
```

### 4.4 Form 130 (New — Replaces Form 16 from FY 2026-27)

```
Key differences from Form 16:
├── First issuance: June 2027 for FY 2026-27
├── Enhanced Part B with more granular deduction breakup
├── QR code for digital verification
├── Employer NPS contribution breakup
└── Regime comparison showing tax under both regimes

Implementation:
├── Build alongside Form 16 generator
├── Feature flag: switch when IT department notifies go-live
└── Employee portal: shows both formats during transition year
```

---

## 5. TDS Reconciliation Engine

### 5.1 Monthly Variance Detection

```
Scheduled: 1st of every month (for previous month)
│
├── For each employee:
│   ├── projected_annual_tax = compute_tax(projected_annual_income)
│   ├── expected_ytd_tds = projected_annual_tax × (months_elapsed / 12)
│   ├── actual_ytd_tds = sum of TDS deducted from salary slips
│   ├── variance = abs(expected - actual) / expected × 100
│   │
│   └── If variance > 10%:
│       ├── Create Compliance Alert (severity = Warning)
│       ├── Reason analysis:
│       │   ├── "Salary increment not reflected in TDS"
│       │   ├── "Bonus paid but TDS not adjusted"
│       │   ├── "Declaration amounts changed after proof submission"
│       │   └── "Manual TDS override detected"
│       └── Recommended action in alert
│
└── Summary report: employees on track vs. off track
```

### 5.2 Year-End Reconciliation

```
Triggered: March (before last payroll of FY)
│
├── For each employee:
│   ├── Compute final annual tax (actual income, verified deductions)
│   ├── Compare with total TDS deducted (Apr-Feb)
│   ├── Difference = shortfall or excess
│   │
│   ├── If shortfall:
│   │   └── Add to March salary slip as additional TDS deduction
│   │
│   └── If excess:
│       └── Two options:
│           ├── Reduce March TDS to zero + carry forward refund note
│           └── Refund through salary (if company policy allows)
│
└── Generate reconciliation report for CA review before 24Q Q4 filing
```

---

## 6. Employee Self-Service Tax Portal

Not a React SPA — Frappe web pages + workspace.

### 6.1 Employee Tax Dashboard (Workspace)

```
My Tax Summary — FY 2026-27
│
├── Regime: New Regime ✓ (declared 05 Apr 2026)
│   └── [Switch Regime] button (only before proof window closes)
│
├── Tax Projection:
│   ├── Estimated Annual Income: Rs 8,50,000
│   ├── Standard Deduction: Rs 75,000
│   ├── Taxable Income: Rs 7,75,000
│   ├── Estimated Tax: Rs 38,750
│   ├── TDS Deducted (YTD): Rs 12,917
│   ├── TDS Remaining: Rs 25,833
│   └── Monthly TDS: Rs 2,870
│
├── Declarations (Old Regime):
│   ├── 80C: Rs 1,50,000 declared / Rs 1,20,000 verified
│   ├── 80D: Rs 25,000 declared / Rs 25,000 verified
│   └── [Upload Proofs] button (when window is open)
│
├── Monthly TDS History:
│   ├── Apr: Rs 3,229 | May: Rs 3,229 | Jun: Rs 3,229 | ...
│   └── Total YTD: Rs 12,917
│
├── Downloads:
│   ├── Form 16 (previous FY) — PDF
│   ├── Monthly Payslips — PDF
│   └── Tax Computation Sheet — PDF
│
└── Help:
    ├── "Which regime is better for me?" — auto-comparison calculator
    └── "What documents do I need for 80C?" — guide
```

### 6.2 Regime Comparison Calculator

```
Employee enters:
├── Annual rent paid
├── 80C investments (PPF, ELSS, insurance, etc.)
├── 80D medical insurance
├── Home loan interest
├── NPS contribution
└── Any other deductions

System shows:
┌────────────────────────┬──────────────┬──────────────┐
│                        │  Old Regime  │  New Regime   │
├────────────────────────┼──────────────┼──────────────┤
│ Gross Salary           │  8,50,000    │  8,50,000     │
│ Standard Deduction     │  (50,000)    │  (75,000)     │
│ HRA Exemption          │  (1,20,000)  │  —            │
│ 80C Deductions         │  (1,50,000)  │  —            │
│ 80D Deductions         │  (25,000)    │  —            │
│ Taxable Income         │  5,05,000    │  7,75,000     │
│ Tax                    │  13,000      │  38,750       │
│ Cess (4%)              │  520         │  1,550        │
│ Total Tax              │  13,520      │  40,300       │
├────────────────────────┼──────────────┼──────────────┤
│ RECOMMENDATION         │  ✓ BETTER    │               │
│ You save               │  Rs 26,780   │               │
└────────────────────────┴──────────────┴──────────────┘
```

---

## 7. Compliance Calendar Integration

Auto-populated deadlines that show in Director Dashboard.

```
FY 2026-27 TDS Calendar:
│
├── Monthly: TDS deposit by 7th of next month (30th April for March)
│
├── Q1 (Apr-Jun): Form 24Q due 31 July 2026
│   └── NEW: Form 138 due 31 July 2026 (first filing under new format)
│
├── Q2 (Jul-Sep): Form 24Q/138 due 31 October 2026
│
├── Q3 (Oct-Dec): Form 24Q/138 due 31 January 2027
│
├── Q4 (Jan-Mar): Form 24Q/138 due 31 May 2027
│   └── Includes Annexure II (full year salary statement)
│
├── Form 16/130: Due 15 June 2027
│
├── Investment Proof Window: typically Jan-Feb (company sets dates)
│
└── Year-end TDS reconciliation: before March payroll
```

---

## 8. Implementation Sequence

```
Week 1-2:  Tax Regime Declaration doctype + enforcement in payroll
           (blocks payroll if no declaration — immediate compliance)

Week 3-4:  TDS Computation Sheet (auto-generated on each salary slip)
           New regime calculator + old regime calculator

Week 5-6:  HRA exemption calculator, 80C/80D/80E declaration workflow
           Investment Proof Window doctype

Week 7-8:  Form 24Q generator (Annexure I for Q1-Q3)
           Challan 281 integration

Week 9-10: Form 24Q Annexure II (Q4 — full year salary statement)
           Form 16 Part A + Part B generator (PDF)

Week 11-12: TDS reconciliation engine (monthly variance + year-end)
            Employee tax dashboard (workspace)

Week 13-14: Regime comparison calculator
            Form 138/130 preparation (skeleton for July 2026 go-live)

Week 14:   External CA validation of all generated forms
```

---

## 9. Data Migration

For companies switching from manual/Excel TDS management:

```
Import Tool:
├── Import employee tax declarations from CSV
├── Import YTD TDS already deducted (for mid-year go-live)
├── Import 80C/80D declarations from previous system
├── Reconcile imported data against salary slips already in HRMS
└── Generate gap report: employees with missing declarations
```
