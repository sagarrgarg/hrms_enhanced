# Phase 3: KSA Framework & People Development

> Knowledge, Skills, and Abilities framework — for the people of the company
> (self-service career growth) and to the people of the company
> (management talent decisions). Extends existing HRMS Skill doctypes.

---

## 1. The Problem

Standard Frappe HRMS has basic skill tracking (`Skill`, `Employee Skill Map`, `Designation Skill`)
but no:
- Competency framework tying skills to roles with proficiency levels
- Skill gap analysis at department/company level
- Career path visualization (what do I need to grow?)
- Connection between skills → performance → training → succession
- Project staffing / bench management for services companies
- Manager tools for team capability assessment

Competitors solving this: Darwinbox (AI-powered skill library), Keka (skill matrix + 9-box grid),
Zoho People (basic competencies).

---

## 2. Architecture

```
hrms_enhanced/ksa/
├── framework.py              # Competency framework management
├── assessment.py             # Skill assessment cycles + workflows
├── gap_analysis.py           # Individual + team + org-level gap computation
├── career_path.py            # Career path engine
├── succession.py             # Succession planning
├── project_staffing.py       # Skill-based resource matching
├── training_needs.py         # Auto-generated training needs from gaps
└── dashboards/
    ├── employee_skills.py    # My Skills dashboard data
    ├── team_capability.py    # Manager's team view
    └── org_skills.py         # HR/Director org-wide view
```

Extends standard HRMS doctypes via custom fields + new doctypes.
Does NOT replace `Skill`, `Employee Skill Map`, or `Designation Skill`.

---

## 3. New Doctypes

### 3.1 Competency Framework

The master structure that defines what competencies matter for each role.

```
Competency Framework
├── name: auto (company-designation-version)
├── company: Link → Company
├── designation: Link → Designation (or "All")
├── department: Link → Department (optional, for department-specific frameworks)
├── version: Int (auto-increment, supports framework evolution)
├── effective_from: Date
├── status: Select [Draft, Active, Archived]
├── approved_by: Link → User
│
├── child: Competency Framework Item
│   ├── competency_type: Select [Knowledge, Skill, Ability, Behavior]
│   ├── skill: Link → Skill (reuses standard HRMS Skill doctype)
│   ├── category: Select [Technical, Functional, Leadership, Behavioral, Domain]
│   ├── required_proficiency: Select [1-Beginner, 2-Developing, 3-Proficient,
│   │                                  4-Advanced, 5-Expert]
│   ├── weight: Percent (how much this competency matters for this role)
│   ├── is_mandatory: Check (must meet minimum to hold this role)
│   └── description: Small Text (what this looks like at the required level)
│
├── total_weight: Percent (auto-calculated, must = 100)
│
└── Workflow:
    Draft → Review (HR Manager) → Active (Director approval)
```

### 3.2 Proficiency Level Definition

What each level (1-5) means — standardized across the organization.

```
Proficiency Level Definition
├── level: Int [1-5]
├── name: Data [Beginner, Developing, Proficient, Advanced, Expert]
├── description: Text
│   1: Understands basic concepts. Needs guidance for tasks. Learning stage.
│   2: Can perform routine tasks independently. Needs help with complex scenarios.
│   3: Independently handles most situations. Can mentor beginners. Solid performer.
│   4: Handles complex/novel situations. Drives improvements. Go-to person.
│   5: Industry-level expertise. Innovates. Sets standards. Teaches advanced topics.
├── observable_behaviors: Text (generic examples)
└── assessment_criteria: Text (how to evaluate this level)
```

### 3.3 Skill Assessment Cycle

Like Appraisal Cycle but for skills — periodic company-wide skill assessment.

```
Skill Assessment Cycle
├── cycle_name: Data (e.g., "H1 2026 Skill Assessment")
├── company: Link → Company
├── start_date: Date
├── end_date: Date
├── status: Select [Draft, Self-Assessment Open, Manager Review, Calibration, Completed]
├── departments: Table MultiSelect → Department (blank = all)
│
├── child: Skill Assessment Cycle Employee
│   ├── employee: Link → Employee
│   ├── designation: Link → Designation (fetched)
│   ├── department: Link → Department (fetched)
│   ├── framework: Link → Competency Framework (auto-matched by designation)
│   ├── self_assessment_status: Select [Pending, Submitted]
│   ├── manager_review_status: Select [Pending, Submitted]
│   ├── overall_proficiency_score: Float (auto-calculated)
│   ├── gap_score: Float (auto: sum of gaps weighted)
│   └── assessment: Link → Skill Assessment (the detailed doc)
│
├── On Complete:
│   ├── Update Employee Skill Map records
│   ├── Generate Training Need Analysis entries
│   └── Update succession readiness scores
│
└── Permissions: HR Manager (full), System Manager (full)
```

### 3.4 Skill Assessment (Enhanced)

Individual assessment document — self + manager + optional peer.

```
Skill Assessment
├── employee: Link → Employee
├── cycle: Link → Skill Assessment Cycle
├── framework: Link → Competency Framework
├── assessment_date: Date
├── status: Select [Draft, Self-Assessment, Manager Review, Final, Disputed]
│
├── child: Skill Assessment Detail
│   ├── skill: Link → Skill
│   ├── competency_type: Data (fetched from framework)
│   ├── category: Data (fetched from framework)
│   ├── required_level: Int (from framework)
│   ├── self_rating: Select [1, 2, 3, 4, 5]
│   ├── self_evidence: Small Text (employee provides examples)
│   ├── manager_rating: Select [1, 2, 3, 4, 5]
│   ├── manager_comments: Small Text
│   ├── final_rating: Select [1, 2, 3, 4, 5] (after calibration)
│   ├── gap: Int (auto: required_level − final_rating, 0 if met)
│   ├── weight: Percent (from framework)
│   └── weighted_gap: Float (auto: gap × weight / 100)
│
├── Section: Peer Feedback (optional)
│   ├── child: Skill Assessment Peer
│   │   ├── peer: Link → Employee
│   │   ├── relationship: Select [Same Team, Cross Team, Reportee, External Stakeholder]
│   │   ├── overall_rating: Select [1-5]
│   │   └── comments: Small Text
│   └── peer_average: Float (auto)
│
├── Section: Summary
│   ├── overall_score: Float (weighted average of final_ratings)
│   ├── total_gap_score: Float (sum of weighted gaps)
│   ├── strengths: Text (auto: skills where final ≥ required)
│   ├── development_areas: Text (auto: skills where final < required)
│   ├── top_3_gaps: Text (auto: highest weighted gaps)
│   └── recommended_training: Text (auto-generated from gap analysis)
│
├── Section: Development Plan
│   ├── child: Development Action Item
│   │   ├── skill: Link → Skill
│   │   ├── action_type: Select [Training, Self-Study, Mentoring, Project Assignment,
│   │   │                         Certification, Job Rotation]
│   │   ├── description: Data
│   │   ├── target_date: Date
│   │   ├── status: Select [Planned, In Progress, Completed, Deferred]
│   │   └── evidence: Small Text
│   └── next_assessment_date: Date
│
└── On Submit: update Employee Skill Map with final_ratings
```

### 3.5 Career Path

Defines progression routes with skill requirements at each level.

```
Career Path
├── path_name: Data (e.g., "Software Engineering Track")
├── department: Link → Department
├── status: Select [Draft, Active, Archived]
│
├── child: Career Path Level
│   ├── sequence: Int (1, 2, 3, ...)
│   ├── designation: Link → Designation
│   ├── grade: Link → Employee Grade
│   ├── typical_experience_years: Int
│   ├── framework: Link → Competency Framework (what's needed at this level)
│   ├── salary_range_min: Currency
│   ├── salary_range_max: Currency
│   └── description: Small Text (what this role does)
│
├── child: Career Path Transition Rule
│   ├── from_level: Int (sequence)
│   ├── to_level: Int (sequence)
│   ├── minimum_time_in_role: Int (months)
│   ├── required_assessment_score: Float (minimum overall score)
│   ├── mandatory_certifications: Small Text
│   └── additional_criteria: Small Text
│
└── Visualization: auto-generated career ladder diagram
```

### 3.6 Succession Plan

```
Succession Plan
├── position: Link → Designation
├── department: Link → Department
├── incumbent: Link → Employee (current holder)
├── risk_of_vacancy: Select [Low, Medium, High, Critical]
├── target_fill_timeline: Select [Immediate, 6 Months, 12 Months, 24 Months]
├── status: Select [Draft, Active, Closed]
│
├── child: Succession Candidate
│   ├── employee: Link → Employee
│   ├── readiness: Select [Ready Now, Ready in 6 Months, Ready in 12 Months,
│   │                       Ready in 24 Months, Developmental]
│   ├── current_assessment_score: Float (from latest Skill Assessment)
│   ├── required_score: Float (from target designation's framework)
│   ├── gap_percentage: Percent (auto)
│   ├── development_plan: Link → Skill Assessment (for the development section)
│   └── notes: Small Text
│
└── Permissions: HR Manager + Director only (sensitive data)
```

### 3.7 Training Need Analysis (Auto-Generated)

```
Training Need Analysis
├── source: Select [Skill Assessment Cycle, Manual, Performance Appraisal]
├── cycle: Link → Skill Assessment Cycle (if auto-generated)
├── department: Link → Department (optional filter)
├── generated_date: Date
├── status: Select [Draft, Approved, In Progress, Completed]
│
├── child: Training Need Item
│   ├── skill: Link → Skill
│   ├── category: Data
│   ├── employees_with_gap: Int (count)
│   ├── average_gap: Float
│   ├── max_gap: Int
│   ├── priority: Select [Critical, High, Medium, Low]
│   │   (auto: Critical if >50% employees have gap ≥2, High if ≥1, etc.)
│   ├── recommended_training_type: Select [Internal Workshop, External Course,
│   │                                       Online Learning, Mentoring, Certification]
│   ├── estimated_cost_per_person: Currency
│   ├── total_estimated_cost: Currency (auto: cost × employees)
│   └── training_program: Link → Training Program (when program is created)
│
├── total_budget_required: Currency (auto-sum)
│
└── On Approve: auto-create Training Programs for high-priority items
```

---

## 4. Employee-Facing Features ("For the People")

### 4.1 My Skills Dashboard

```
My Skills — Workspace Page
│
├── Profile Card:
│   ├── Employee photo, name, designation, department
│   ├── Overall Proficiency Score: 3.7 / 5.0
│   ├── Skills Count: 12 assessed, 3 gaps, 2 certifications
│   └── Last Assessment: January 2026
│
├── Skill Radar Chart:
│   └── Spider/radar chart showing:
│       ├── Required level (blue line — from Competency Framework)
│       └── Actual level (green fill — from latest assessment)
│       Visual gap where green doesn't reach blue
│
├── My Competencies (table):
│   ├── Skill Name | Category | Required | My Level | Gap | Status
│   ├── Python     | Technical | 4        | 4       | 0   | ✅ Met
│   ├── SQL        | Technical | 3        | 2       | 1   | ⚠️ Gap
│   ├── Leadership | Behavioral| 2        | 1       | 1   | ⚠️ Gap
│   └── ...
│
├── My Career Path:
│   ├── Current: Software Engineer (Level 2)
│   ├── Next: Senior Software Engineer (Level 3)
│   ├── Requirements for next level:
│   │   ├── ✅ Python ≥ 4 (you: 4)
│   │   ├── ❌ SQL ≥ 3 (you: 2) — "Recommended: Advanced SQL course"
│   │   ├── ❌ Leadership ≥ 2 (you: 1) — "Recommended: Mentoring program"
│   │   └── ⏳ Minimum 18 months in role (you: 14 months)
│   └── Estimated readiness: 6 months (based on development plan)
│
├── My Development Plan:
│   ├── Active actions from latest Skill Assessment
│   ├── Status: 2/5 completed, 1 in progress, 2 planned
│   └── Quick update buttons (mark progress)
│
├── My Certifications:
│   ├── AWS Solutions Architect — Valid until Dec 2027
│   ├── PMP — Valid until Mar 2028
│   └── [Add Certification] button
│
└── Skill Endorsements:
    ├── "Priya endorsed you for Python (Advanced)" — 2 days ago
    ├── "Rahul endorsed you for Code Review (Proficient)" — 1 week ago
    └── [Endorse a Colleague] button
```

### 4.2 Self-Assessment Flow

```
Employee receives notification: "Skill Assessment Cycle H1 2026 is open"
│
├── Step 1: Review framework
│   └── See all competencies expected for their designation
│       with descriptions of what each level looks like
│
├── Step 2: Self-rate each competency (1-5)
│   └── For each, provide evidence:
│       "Designed and implemented the payment gateway integration
│        independently, handling edge cases for 3 payment providers"
│
├── Step 3: Review & submit
│   └── See summary: overall score, gaps identified
│       Option to add notes for manager
│
├── Step 4: Manager reviews (notification to manager)
│   └── Manager sees self-ratings, adjusts if needed,
│       adds comments, submits
│
├── Step 5: Calibration (HR facilitates if needed)
│   └── Cross-team calibration meeting
│       Adjust final ratings for consistency
│
└── Step 6: Results shared with employee
    └── Development plan created collaboratively
```

### 4.3 Skill Endorsement

Lightweight peer recognition — like LinkedIn endorsements but internal.

```
Skill Endorsement (simple doctype)
├── endorser: Link → Employee (auto: session user's employee)
├── endorsed_employee: Link → Employee
├── skill: Link → Skill
├── proficiency_level: Select [Beginner, Developing, Proficient, Advanced, Expert]
├── context: Small Text ("Saw them handle the X project brilliantly")
├── endorsed_on: Date (auto)
│
└── Rules:
    ├── Cannot endorse yourself
    ├── Cannot endorse same person for same skill twice in 6 months
    ├── Endorsement count shown on Employee Skill Map
    └── Top endorsed skills highlighted in My Skills dashboard
```

### 4.4 Employee Certification Tracker

```
Employee Certification (child table on Employee or standalone)
├── employee: Link → Employee
├── certification_name: Data
├── issuing_body: Data
├── certification_id: Data
├── skill: Link → Skill (maps to competency framework)
├── issue_date: Date
├── expiry_date: Date (optional)
├── attachment: Attach (certificate copy)
├── verification_status: Select [Uploaded, Verified, Expired]
├── verified_by: Link → User
│
└── Scheduled: alert 60 days before expiry
    "Your AWS Solutions Architect certification expires on Dec 15, 2027.
     Renewal recommended."
```

---

## 5. Management-Facing Features ("To the People")

### 5.1 Team Capability Dashboard (for Managers)

```
My Team Skills — Workspace Page
│
├── Team Overview:
│   ├── Team size: 8 direct reports
│   ├── Average proficiency: 3.2 / 5.0
│   ├── Critical gaps: 3 (skills where >50% team is below required)
│   └── Assessments pending: 2 employees
│
├── Team Skill Heat Map:
│   ┌──────────────┬─────────┬─────┬──────────┬───────┐
│   │ Employee     │ Python  │ SQL │ System   │ Comm  │
│   │              │ (req:4) │(r:3)│ Design(3)│  (3)  │
│   ├──────────────┼─────────┼─────┼──────────┼───────┤
│   │ Amit         │ 🟢 4    │ 🟢 3│ 🟡 2     │ 🟢 3  │
│   │ Priya        │ 🟢 5    │ 🟢 4│ 🟢 3     │ 🟢 4  │
│   │ Rahul        │ 🟡 3    │ 🔴 1│ 🔴 1     │ 🟡 2  │
│   │ Sneha        │ 🟢 4    │ 🟡 2│ 🟡 2     │ 🟢 3  │
│   └──────────────┴─────────┴─────┴──────────┴───────┘
│   Colors: 🟢 meets/exceeds  🟡 close (gap=1)  🔴 significant gap (gap≥2)
│
├── Critical Gaps (highest priority):
│   ├── SQL: 2/4 team members below required (Rahul: gap 2, Sneha: gap 1)
│   ├── System Design: 3/4 below required
│   └── [Create Training Request] button per gap
│
├── Succession Readiness:
│   ├── If you leave, who can step up?
│   ├── Priya: 85% ready (gap: Leadership only)
│   └── Amit: 60% ready (gaps: System Design, Team Management)
│
└── Pending Actions:
    ├── Review Rahul's self-assessment (submitted 3 days ago)
    ├── Approve Sneha's certification upload
    └── Schedule Amit's development plan review
```

### 5.2 Organization Skill Map (for HR/Directors)

```
Org Skills — Workspace Page
│
├── Company Skill Distribution:
│   ├── Pie chart: Technical (45%) / Functional (25%) / Leadership (15%) / Behavioral (15%)
│   └── Average proficiency by category
│
├── Department Comparison:
│   ├── Bar chart: avg proficiency per department vs required
│   └── Departments with highest gap highlighted
│
├── Skill Inventory:
│   ├── Table: Skill | Employees With Skill | Avg Proficiency | % Meeting Required
│   ├── Python: 45 employees, avg 3.5, 78% meeting required
│   ├── SQL: 38 employees, avg 2.8, 52% meeting required ← flag
│   └── Filter by: department, category, gap severity
│
├── Bench View (for services companies):
│   ├── Available employees (not on project / notice period)
│   ├── Filtered by skill requirements
│   ├── Match score per employee vs. project needs
│   └── Utilization rate per employee
│
├── Training Investment:
│   ├── Budget allocated vs. spent
│   ├── Training hours per employee (avg)
│   ├── Skill improvement after training (before vs. after scores)
│   └── ROI: cost per proficiency-level improvement
│
└── 9-Box Grid (Performance × Potential):
    ┌────────────┬────────────┬────────────┐
    │ Enigma     │ Growth     │ Star       │  High
    │ (Low perf, │ Employee   │ (High perf,│  Potential
    │  Hi pot)   │            │  Hi pot)   │
    ├────────────┼────────────┼────────────┤
    │ Dilemma    │ Core       │ High       │  Medium
    │            │ Player     │ Performer  │  Potential
    ├────────────┼────────────┼────────────┤
    │ Risk       │ Average    │ Solid      │  Low
    │            │ Performer  │ Performer  │  Potential
    └────────────┴────────────┴────────────┘
     Low Perf    Med Perf     High Perf

    Populated from: Appraisal score (performance) × Skill Assessment gap (potential)
    Click any box → see employees in that quadrant
```

### 5.3 Project Staffing Engine (for Services/IT Companies)

```
Project Staffing Request
├── project_name: Data
├── client: Link → Customer (optional)
├── department: Link → Department
├── start_date: Date
├── end_date: Date
├── status: Select [Open, Partially Filled, Filled, Closed]
│
├── child: Staffing Requirement
│   ├── role_title: Data (e.g., "Senior Backend Developer")
│   ├── designation: Link → Designation
│   ├── headcount: Int
│   ├── skills_required: Table MultiSelect → Skill
│   ├── minimum_proficiency: Select [1-5]
│   ├── allocated_employee: Link → Employee (filled when matched)
│   └── match_score: Percent (auto-calculated)
│
└── [Find Matches] button:
    Returns ranked list of available employees
    Score = weighted match of required skills × proficiency
    Filters: available, not on notice period, not on leave
```

---

## 6. Integration Points

### 6.1 KSA ↔ Performance Appraisal

```
On Appraisal Submit:
├── Pull employee's latest Skill Assessment scores
├── Auto-populate competency section in appraisal
├── Appraisal overall rating feeds into 9-Box Grid (performance axis)
└── Skill Assessment gap feeds into 9-Box Grid (potential axis)
```

### 6.2 KSA ↔ Training

```
On Skill Assessment Cycle Complete:
├── Auto-generate Training Need Analysis
├── For each skill with >3 employees having gap ≥ 2:
│   └── Recommend creating a Training Program
├── After Training Event completion:
│   └── Prompt reassessment of trained skills
└── Track: did the training actually close the gap?
```

### 6.3 KSA ↔ Recruitment

```
On Job Opening Create:
├── Auto-populate required skills from Competency Framework for that designation
├── Interview feedback: rate candidate on each required skill
├── Match score: candidate skills vs. framework requirements
└── On Employee Onboarding: create initial Skill Assessment from interview data
```

### 6.4 KSA ↔ Employee Transfer/Promotion

```
On Transfer/Promotion Request:
├── Check: does employee meet Competency Framework for target designation?
├── If gap exists: show gaps and require acknowledgment
├── Auto-suggest development plan for transition
└── After transfer: schedule skill assessment in 3 months
```

---

## 7. Implementation Sequence

```
Week 1-2:  Proficiency Level Definition + Competency Framework doctypes
           Custom fields on existing Skill, Employee Skill Map

Week 3-4:  Skill Assessment Cycle + Skill Assessment (enhanced) doctypes
           Self-assessment workflow

Week 5-6:  Manager review workflow + calibration support
           Auto-update Employee Skill Map on assessment submit

Week 7-8:  Gap analysis engine (individual + team + org)
           Training Need Analysis auto-generation

Week 9-10: Career Path doctype + visualization
           Employee Skills Dashboard (My Skills workspace)

Week 11-12: Team Capability Dashboard (manager workspace)
            Org Skills Dashboard (HR workspace)

Week 13-14: Succession Plan doctype
            9-Box Grid computation and visualization

Week 15-16: Skill Endorsement, Certification Tracker
            Project Staffing Engine (optional, for services companies)

Week 16:   Integration hooks (appraisal, training, recruitment, transfer)
```

---

## 8. Extending Standard HRMS (Custom Fields)

Instead of new doctypes where possible, add custom fields to existing:

```
Employee:
├── overall_proficiency_score: Float (auto from latest assessment)
├── last_skill_assessment_date: Date
├── career_path: Link → Career Path
├── career_path_level: Int (current level in career path)
└── succession_readiness: Select [Not Assessed, Developmental, Ready 24M,
                                   Ready 12M, Ready 6M, Ready Now]

Employee Skill Map:
├── assessment_date: Date (when was this last assessed)
├── assessed_by: Link → User
├── endorsement_count: Int
└── evidence: Small Text

Skill:
├── category: Select [Technical, Functional, Leadership, Behavioral, Domain]
├── is_certifiable: Check
└── related_training_programs: Table MultiSelect → Training Program

Training Event:
├── target_skills: Table MultiSelect → Skill
├── expected_proficiency_gain: Int (levels)
└── post_training_assessment_date: Date

Appraisal:
├── competency_score: Float (from latest Skill Assessment)
├── potential_rating: Select [Low, Medium, High]
└── nine_box_position: Data (auto: "Star", "Core Player", etc.)
```
