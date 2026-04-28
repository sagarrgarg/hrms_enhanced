# Phase 1: Indian Compliance Engine

> Legal necessity. Prevents fraud (Finance Head case), automates statutory deductions,
> generates filing-ready reports. Data-driven rules — HR updates slabs, not developers.

---

## 1. Architecture

```
hrms_enhanced/compliance/
├── engine.py                 # Salary Slip hooks (validate, before_submit)
├── guardrails.py             # Self-processing block, zero-TDS alert, exit gate
├── calculators/
│   ├── esi.py                # ESI eligibility + calculation
│   ├── professional_tax.py   # State-wise PT engine
│   ├── lwf.py                # Labour Welfare Fund per state
│   ├── minimum_wage.py       # Minimum wage validation
│   ├── gratuity.py           # Enhanced gratuity (Labour Codes 2020)
│   └── bonus.py              # Payment of Bonus Act
├── filing/
│   ├── ecr_generator.py      # PF ECR file generation
│   ├── esi_challan.py        # ESI challan generation
│   ├── pt_return.py          # PT return per state
│   └── lwf_return.py         # LWF return per state
└── dashboard.py              # Director compliance dashboard
```

Integration pattern — hooks on standard HRMS, no override classes:

```python
# hooks.py additions
doc_events = {
    "Employee Checkin": {...},  # existing
    "Salary Slip": {
        "validate": "hrms_enhanced.compliance.engine.validate_salary_slip",
        "before_submit": "hrms_enhanced.compliance.engine.before_submit_salary_slip",
    },
    "Payroll Entry": {
        "on_submit": "hrms_enhanced.compliance.engine.on_payroll_submit",
    },
    "Full and Final Statement": {
        "before_submit": "hrms_enhanced.compliance.guardrails.exit_compliance_gate",
    },
    "Employee": {
        "validate": "hrms_enhanced.compliance.guardrails.validate_employee_type_change",
    },
}
```

---

## 2. New Doctypes

### 2.1 State Compliance Rule

Master doctype. One record per state per rule type per effective date.
HR manager updates when laws change — no code deployment.

```
State Compliance Rule
├── state: Link → State (India)
├── rule_type: Select [Professional Tax, LWF, Minimum Wage, ESI Threshold, Bonus]
├── effective_from: Date (required)
├── effective_to: Date (optional — blank = current)
├── frequency: Select [Monthly, Quarterly, Half-Yearly, Yearly]
├── notes: Small Text (law reference, gazette notification number)
│
├── child: State Compliance Slab
│   ├── from_amount: Currency
│   ├── to_amount: Currency (0 = unlimited)
│   ├── rate_type: Select [Fixed Amount, Percentage]
│   ├── rate_or_amount: Float
│   ├── annual_cap: Currency (0 = no cap)
│   └── special_month_amount: Currency (e.g., PT February adjustment)
│
├── child: State Compliance Exemption
│   ├── exemption_type: Select [Gender, Age, Disability, Category, Salary Below]
│   ├── value: Data (e.g., "Female", "65+", "Rs 25000")
│   └── description: Data
│
└── Permissions: HR Manager (CRUD), System Manager (full)
```

**Pre-loaded data for all 28 states + 8 UTs:**
- Professional Tax slabs (Maharashtra, Karnataka, Tamil Nadu, West Bengal, AP, Telangana, etc.)
- LWF amounts (16 applicable states)
- Minimum wages (central floor + state-wise)

### 2.2 ESI Configuration

```
ESI Configuration
├── effective_from: Date
├── wage_ceiling: Currency (currently Rs 21,000)
├── disability_ceiling: Currency (currently Rs 25,000)
├── employee_rate: Percent (currently 0.75%)
├── employer_rate: Percent (currently 3.25%)
├── coverage_threshold: Int (currently 10 employees)
├── wage_components_included: Table MultiSelect → Salary Component
├── wage_components_excluded: Table MultiSelect → Salary Component
└── Permissions: HR Manager (CRUD), System Manager (full)
```

### 2.3 PF Configuration (Enhanced)

Standard HRMS has basic PF. Enhance with:

```
PF Enhanced Configuration
├── effective_from: Date
├── wage_ceiling: Currency (Rs 15,000, may increase to 21-25K)
├── employee_rate: Percent (12%)
├── employer_epf_rate: Percent (3.67%)
├── employer_eps_rate: Percent (8.33%)
├── edli_rate: Percent (0.5%)
├── admin_charges_rate: Percent (0.5%)
├── international_worker_rules: Check (no ceiling if checked)
├── voluntary_pf_allowed: Check
└── ecr_format_version: Select [v2.0, v2.1]
```

### 2.4 Compliance Filing Log

Tracks every statutory filing — what was filed, when, for which period.

```
Compliance Filing Log
├── filing_type: Select [PF ECR, ESI Challan, PT Return, LWF Return, TDS 24Q, Form 16]
├── period_from: Date
├── period_to: Date
├── state: Link → State (for PT/LWF)
├── filing_date: Date
├── due_date: Date
├── status: Select [Draft, Generated, Filed, Acknowledged, Late]
├── file_attachment: Attach (the generated file)
├── amount: Currency
├── employee_count: Int
├── reference_number: Data (challan/acknowledgement number)
├── filed_by: Link → User
├── notes: Small Text
└── Permissions: HR Manager (CRUD), System Manager (full)
```

### 2.5 Compliance Alert

Auto-generated alerts for directors/HR when something needs attention.

```
Compliance Alert
├── alert_type: Select [Zero TDS, Self Processing, Missing Declaration, TDS Variance,
│                       Minimum Wage Violation, ESI Threshold Breach, Filing Overdue,
│                       Employment Type Change, Exit Compliance Gap]
├── severity: Select [Critical, Warning, Info]
├── employee: Link → Employee (if applicable)
├── salary_slip: Link → Salary Slip (if applicable)
├── description: Text
├── recommended_action: Text
├── status: Select [Open, Acknowledged, Resolved, Ignored]
├── resolved_by: Link → User
├── resolved_at: Datetime
├── resolution_notes: Small Text
└── Permissions: HR Manager (read, write), System Manager (full)
    Notification: auto-email to Director on Critical alerts
```

---

## 3. Compliance Guardrails (Fraud Prevention)

Directly from the Finance Head case analysis.

### 3.1 Self-Processing Block

```python
# guardrails.py

def validate_salary_slip(doc, method):
    """Block employees from processing their own Salary Slip."""
    if doc.employee == frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name"):
        if not frappe.has_permission("Salary Slip", "submit", raise_exception=False,
                                     user="Administrator"):
            create_compliance_alert(
                alert_type="Self Processing",
                severity="Critical",
                employee=doc.employee,
                salary_slip=doc.name,
                description=f"{doc.employee_name} attempted to process their own salary slip",
            )
            frappe.throw(
                "You cannot process your own Salary Slip. "
                "This requires approval from another authorized user.",
                title="Self-Processing Blocked"
            )
```

### 3.2 Zero-TDS Alert

```python
def before_submit_salary_slip(doc, method):
    """Alert if high-salary employee has zero TDS."""
    annual_salary = estimate_annual_salary(doc.employee)
    basic_exemption = 250000  # new regime basic exemption

    if annual_salary > basic_exemption:
        tds_amount = get_tds_from_slip(doc)
        if tds_amount == 0:
            create_compliance_alert(
                alert_type="Zero TDS",
                severity="Critical",
                employee=doc.employee,
                salary_slip=doc.name,
                description=(
                    f"{doc.employee_name} has annual salary Rs {annual_salary:,.0f} "
                    f"but Rs 0 TDS in this payslip. "
                    f"Verify tax regime declaration and deductions."
                ),
                recommended_action=(
                    "1. Verify employee has declared tax regime (Old/New)\n"
                    "2. Check if valid 192 exemption exists\n"
                    "3. If not, do not release salary until TDS is computed\n"
                    "4. Consult external CA if unsure"
                ),
            )
            # Block submission — require director override
            frappe.throw(
                f"Cannot submit: {doc.employee_name} has Rs 0 TDS on "
                f"Rs {annual_salary:,.0f} annual salary. "
                f"Director or System Manager must review and override.",
                title="Zero TDS — Compliance Block"
            )
```

### 3.3 Employment Type Lock

```python
def validate_employee_type_change(doc, method):
    """Require director approval for employment type changes."""
    if doc.is_new():
        return

    old_type = doc.db_get("employment_type")
    if old_type and old_type != doc.employment_type:
        if not user_has_role(frappe.session.user, "Director"):
            create_compliance_alert(
                alert_type="Employment Type Change",
                severity="Warning",
                employee=doc.name,
                description=(
                    f"Employment type change attempted: {old_type} → {doc.employment_type}. "
                    f"This affects TDS section (192 vs 194C). Requires Director approval."
                ),
            )
            frappe.throw(
                "Changing employment type (Salaried ↔ Contractual) requires Director approval. "
                "This affects TDS sections and statutory compliance.",
                title="Employment Type Change — Approval Required"
            )
```

### 3.4 Exit Compliance Gate

```python
def exit_compliance_gate(doc, method):
    """Block F&F submission if compliance gaps exist."""
    gaps = []

    # Check TDS reconciled
    tds_status = verify_tds_reconciled(doc.employee, doc.resignation_date)
    if not tds_status["reconciled"]:
        gaps.append(f"TDS shortfall of Rs {tds_status['shortfall']:,.0f} for current FY")

    # Check Form 16 generated
    if not form_16_exists(doc.employee, current_fy()):
        gaps.append("Form 16 not generated for current financial year")

    # Check PF contributions up to date
    pf_status = verify_pf_current(doc.employee)
    if not pf_status["current"]:
        gaps.append(f"PF contributions pending for {pf_status['months']} months")

    # Check gratuity calculated (if eligible)
    if is_gratuity_eligible(doc.employee):
        if not doc.gratuity_amount:
            gaps.append("Gratuity not calculated (employee eligible with 5+ years)")

    if gaps:
        gap_list = "\n".join(f"  • {g}" for g in gaps)
        frappe.throw(
            f"Cannot submit Full & Final — compliance gaps:\n{gap_list}\n\n"
            f"Resolve all gaps before processing exit.",
            title="Exit Compliance Gate"
        )
```

### 3.5 Minimum Wage Validator

```python
def validate_minimum_wage(doc, method):
    """Block payroll if net salary falls below applicable minimum wage."""
    state = get_employee_state(doc.employee)
    min_wage = get_minimum_wage(state, doc.posting_date)

    if min_wage and doc.gross_pay < min_wage:
        create_compliance_alert(
            alert_type="Minimum Wage Violation",
            severity="Critical",
            employee=doc.employee,
            salary_slip=doc.name,
            description=(
                f"Gross pay Rs {doc.gross_pay:,.0f} is below minimum wage "
                f"Rs {min_wage:,.0f} for {state}."
            ),
        )
        frappe.throw(
            f"Gross pay Rs {doc.gross_pay:,.0f} is below the minimum wage "
            f"Rs {min_wage:,.0f} for {state}. Cannot process payroll.",
            title="Minimum Wage Violation"
        )
```

---

## 4. Calculation Engines

### 4.1 ESI Calculator

```python
# calculators/esi.py

def calculate_esi(employee, gross_wages, posting_date):
    """
    ESI calculation based on current configuration.
    Returns dict with employee_contribution, employer_contribution, is_applicable.
    """
    config = get_active_esi_config(posting_date)

    ceiling = config.wage_ceiling
    if is_disabled_employee(employee):
        ceiling = config.disability_ceiling

    if gross_wages > ceiling:
        return {"is_applicable": False, "reason": "Gross wages exceed ceiling"}

    company_employee_count = get_company_employee_count(employee)
    if company_employee_count < config.coverage_threshold:
        return {"is_applicable": False, "reason": "Company below coverage threshold"}

    return {
        "is_applicable": True,
        "employee_contribution": round(gross_wages * config.employee_rate / 100, 0),
        "employer_contribution": round(gross_wages * config.employer_rate / 100, 0),
        "gross_wages": gross_wages,
        "ceiling_applied": ceiling,
    }
```

### 4.2 Professional Tax Engine

```python
# calculators/professional_tax.py

def calculate_professional_tax(employee, gross_salary, state, posting_date, month):
    """
    State-wise PT calculation from State Compliance Rule records.
    Handles monthly, half-yearly, February adjustment, and exemptions.
    """
    rule = get_active_rule(state, "Professional Tax", posting_date)
    if not rule:
        return {"amount": 0, "reason": f"No PT rule found for {state}"}

    # Check exemptions (gender, age, disability, salary floor)
    exemption = check_exemptions(employee, rule)
    if exemption:
        return {"amount": 0, "reason": exemption}

    # Find applicable slab
    slab = find_slab(rule, gross_salary)
    if not slab:
        return {"amount": 0, "reason": "Salary below PT threshold"}

    amount = slab.rate_or_amount
    if slab.rate_type == "Percentage":
        amount = round(gross_salary * slab.rate_or_amount / 100, 0)

    # February adjustment (Maharashtra, Karnataka pattern)
    if month == 2 and slab.special_month_amount:
        amount = slab.special_month_amount

    # Annual cap enforcement
    if slab.annual_cap:
        ytd_pt = get_ytd_pt_deducted(employee, posting_date)
        if ytd_pt + amount > slab.annual_cap:
            amount = max(0, slab.annual_cap - ytd_pt)

    return {
        "amount": amount,
        "state": state,
        "slab_from": slab.from_amount,
        "slab_to": slab.to_amount,
        "frequency": rule.frequency,
    }
```

### 4.3 LWF Calculator

```python
# calculators/lwf.py

def calculate_lwf(employee, state, posting_date, payroll_month):
    """
    Labour Welfare Fund — fixed amounts per state.
    Only deduct in the correct month(s) based on state frequency.
    """
    rule = get_active_rule(state, "LWF", posting_date)
    if not rule:
        return {"applicable": False}

    # Check if this is a deduction month for this state
    if not is_lwf_deduction_month(state, rule.frequency, payroll_month):
        return {"applicable": False, "reason": "Not a deduction month for this state"}

    slab = rule.slabs[0] if rule.slabs else None
    if not slab:
        return {"applicable": False}

    return {
        "applicable": True,
        "employee_contribution": slab.rate_or_amount,  # fixed amount
        "employer_contribution": slab.special_month_amount or slab.rate_or_amount,
        "state": state,
        "frequency": rule.frequency,
    }
```

---

## 5. Filing Generators

### 5.1 PF ECR Generator

```python
# filing/ecr_generator.py

@frappe.whitelist()
def generate_ecr(month, year, company):
    """
    Generate EPFO Electronic Challan cum Return (ECR) file.
    Format: UAN, Member Name, Gross Wages, EPF Wages, EPS Wages, EDLI Wages,
            EPF Contribution, EPS Contribution, Difference (EPF-EPS),
            NCP Days, Refund of Advances
    """
    employees = get_pf_eligible_employees(company, month, year)
    rows = []

    for emp in employees:
        slip = get_salary_slip(emp.name, month, year)
        if not slip:
            continue

        pf_wages = min(slip.basic + slip.da, pf_ceiling)
        epf = round(pf_wages * 0.12, 0)
        eps = round(min(pf_wages, 15000) * 0.0833, 0)

        rows.append({
            "uan": emp.provident_fund_account,
            "member_name": emp.employee_name,
            "gross_wages": slip.gross_pay,
            "epf_wages": pf_wages,
            "eps_wages": min(pf_wages, 15000),
            "edli_wages": min(pf_wages, 15000),
            "epf_contribution": epf,
            "eps_contribution": eps,
            "epf_eps_diff": epf - eps,
            "ncp_days": get_ncp_days(emp.name, month, year),
            "refund": 0,
        })

    # Generate text file in EPFO prescribed format
    ecr_content = format_ecr_file(rows)

    # Save as attachment + create filing log
    file_doc = save_filing_attachment(ecr_content, f"ECR_{month}_{year}.txt")
    create_filing_log("PF ECR", month, year, len(rows), file_doc.file_url)

    return {"employee_count": len(rows), "file_url": file_doc.file_url}
```

### 5.2 ESI Challan Generator

```python
# filing/esi_challan.py

@frappe.whitelist()
def generate_esi_challan(month, year, company):
    """Generate ESI contribution challan data for filing."""
    employees = get_esi_eligible_employees(company, month, year)
    rows = []

    for emp in employees:
        slip = get_salary_slip(emp.name, month, year)
        if not slip:
            continue

        esi = calculate_esi(emp.name, slip.gross_pay, slip.posting_date)
        if not esi["is_applicable"]:
            continue

        rows.append({
            "ip_number": emp.esi_number,
            "ip_name": emp.employee_name,
            "no_of_days": get_working_days(emp.name, month, year),
            "total_wages": slip.gross_pay,
            "ip_contribution": esi["employee_contribution"],
            "employer_contribution": esi["employer_contribution"],
        })

    file_doc = save_filing_attachment(
        format_esi_challan(rows), f"ESI_Challan_{month}_{year}.csv"
    )
    create_filing_log("ESI Challan", month, year, len(rows), file_doc.file_url)

    return {"employee_count": len(rows), "file_url": file_doc.file_url}
```

---

## 6. Director Compliance Dashboard

Workspace page — no React needed, pure Frappe workspace with number cards + charts.

```
Compliance Health Dashboard
│
├── Number Cards:
│   ├── TDS Compliance %: (employees with correct TDS / total) × 100
│   ├── Open Compliance Alerts: count of unresolved Critical + Warning alerts
│   ├── Pending Filings: filings past due date with status != Filed
│   └── Employees Below Minimum Wage: count (should always be 0)
│
├── Alerts Table:
│   └── Recent Compliance Alerts (Critical first, sorted by date)
│       Columns: severity, type, employee, description, status
│
├── Filing Calendar:
│   ├── PF ECR: due 15th monthly (status indicator)
│   ├── ESI Challan: due 15th monthly
│   ├── PT Return: state-wise due dates
│   ├── TDS 24Q: quarterly due dates (Jul 31, Oct 31, Jan 31, May 31)
│   └── LWF: state-wise annual/half-yearly
│
├── Monthly TDS Variance Chart:
│   └── Bar chart: projected vs actual TDS per month (flags >10% variance)
│
└── Quick Actions:
    ├── Generate ECR (this month)
    ├── Generate ESI Challan (this month)
    ├── Run TDS Reconciliation
    └── View All Alerts
```

---

## 7. Pre-loaded Compliance Data

Ship with data for immediate use — no manual setup.

### Professional Tax (all applicable states)

| State | Monthly Slab Example | February Adj | Women Exemption |
|-------|---------------------|--------------|-----------------|
| Maharashtra | >10K: Rs 200/month | Rs 300 in Feb | Exempt up to Rs 25K |
| Karnataka | >15K: Rs 200/month | Rs 300 in Feb | No |
| West Bengal | >10K: Rs 110/month | No | No |
| Tamil Nadu | Half-yearly deduction | Aug + Jan only | No |
| Andhra Pradesh | >20K: Rs 200/month | No | No |
| Telangana | >20K: Rs 200/month | No | No |
| Gujarat | >12K: Rs 200/month | No | No |
| Kerala | >Varies by half-year | Half-yearly | No |
| ... | (all 18 PT-applicable states) | | |

### LWF (16 applicable states)

| State | Employee | Employer | Frequency | Threshold |
|-------|----------|----------|-----------|-----------|
| Maharashtra | Rs 25 | Rs 75 | Half-yearly (Jun + Dec) | 5 employees |
| Karnataka | Rs 50 | Rs 100 | Annual (Jan) | 10 employees |
| Tamil Nadu | Rs 10 | Rs 20 | Annual (Jan) | 10 employees |
| Gujarat | Rs 6 | Rs 12 | Half-yearly | 5 employees |
| ... | | | | |

### Minimum Wages (central + major states)

| State/Central | Unskilled | Semi-skilled | Skilled | Highly Skilled |
|---------------|-----------|-------------|---------|----------------|
| Central Floor | Rs 20,358 | — | — | — |
| Delhi | Rs 18,456 | Rs 20,426 | Rs 22,411 | Rs 24,398 |
| Maharashtra | Rs 14,750 | Rs 15,750 | Rs 16,750 | Rs 17,750 |
| Karnataka | Rs 13,500 | Rs 14,500 | Rs 15,750 | Rs 17,000 |
| ... | | | | |

---

## 8. Implementation Sequence

```
Week 1-2:  Doctypes — State Compliance Rule, ESI Configuration, PF Enhanced,
           Compliance Alert, Compliance Filing Log
           Pre-load PT + LWF + min wage data for all states

Week 3-4:  Guardrails — Self-processing block, zero-TDS alert, employment type lock
           (immediate fraud prevention, no calculation logic needed)

Week 5-6:  Calculators — ESI engine, PT state engine, LWF engine
           Hook into Salary Slip validate/before_submit

Week 7-8:  Calculators — minimum wage validator, gratuity enhancement,
           Labour Codes 50% basic rule validator

Week 9-10: Filing — ECR generator, ESI challan generator, PT return generator

Week 11-12: Dashboard — Director compliance workspace, number cards, alert table,
            filing calendar, TDS variance chart

Week 12:   Testing with real payroll data, external CA review of calculations
```

---

## 9. Testing Strategy

- **Unit tests**: Each calculator with known slab inputs → expected outputs
- **State-wise tests**: PT calculation for all 18 states with edge cases (February, women, age 65+)
- **Integration tests**: Full Salary Slip with all deductions applied correctly
- **Guardrail tests**: Self-processing blocked, zero-TDS blocked, employment type locked
- **Filing tests**: ECR format matches EPFO specification, ESI challan format correct
- **Regression**: Standard HRMS payroll still works when hrms_enhanced is installed
- **External validation**: CA firm reviews first 2 months of generated filings
