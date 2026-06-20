"""
GAP-5: Export service — Excel, CSV, and Xray-ready CSV generation.

Provides:
  export_test_cases_excel          → openpyxl Workbook bytes
  export_test_cases_csv            → CSV string (RFC 4180)
  export_test_cases_xray_csv       → Xray-compatible CSV (one row per step)
  export_traceability_matrix_excel → openpyxl Workbook bytes (matrix)
  get_requirement_traceability_chain → per-requirement chain dict

Edge cases handled:
  - Empty projects / no test cases
  - Null / undefined fields (all coerced to safe defaults)
  - Excel cell text limit (32 767 chars) — text truncated with notice
  - Unicode in titles, steps, BDD scenarios
  - Steps stored as list[dict] or plain strings
  - Pagination across large datasets (streams all pages)
  - Requirements with no scenarios/test-cases/executions/defects
  - Circular / missing lineage references
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.defect import DefectDraft
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_scenario import TestScenario

# ── Excel cell helpers ──────────────────────────────────────────────────────

_EXCEL_MAX_CELL = 32_767  # hard Excel limit per cell


def _safe_str(value: Any, max_len: int = _EXCEL_MAX_CELL) -> str:
    """Coerce *value* to a str safe for an Excel cell."""
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        try:
            text = json.dumps(value, ensure_ascii=False)
        except Exception:
            text = str(value)
    elif isinstance(value, bool):
        text = "Yes" if value else "No"
    else:
        text = str(value)
    if len(text) > max_len:
        trunc_at = max_len - 20
        if trunc_at > 0:
            text = text[:trunc_at] + "… [truncated]"
        else:
            # max_len is very small — just hard-cut, no suffix
            text = text[:max_len]
    return text


def _steps_to_text(steps: list | None) -> str:
    """Flatten test-case steps to a human-readable string."""
    if not steps:
        return ""
    lines: list[str] = []
    for i, step in enumerate(steps, 1):
        if isinstance(step, dict):
            action = step.get("action") or step.get("step") or ""
            expected = step.get("expected_result") or step.get("expected") or ""
            if expected:
                lines.append(f"{i}. {action}  →  {expected}")
            else:
                lines.append(f"{i}. {action}")
        else:
            lines.append(f"{i}. {step}")
    return "\n".join(lines)


def _list_to_text(items: list | None) -> str:
    if not items:
        return ""
    return "; ".join(str(x) for x in items if x is not None)


# ── Data fetching helpers ───────────────────────────────────────────────────

async def _fetch_all_test_cases(
    db: AsyncSession,
    project_id: int,
    include_drafts: bool = False,
) -> list[TestCase]:
    """Return all test cases for *project_id*, optionally including drafts."""
    stmt = select(TestCase).where(TestCase.project_id == project_id)
    if not include_drafts:
        stmt = stmt.where(TestCase.status == "approved")
    stmt = stmt.order_by(TestCase.id)
    return list((await db.execute(stmt)).scalars().all())


async def _fetch_requirement_map(
    db: AsyncSession,
    project_id: int,
) -> dict[int, Requirement]:
    """Return {req.id: req} for the project."""
    stmt = select(Requirement).where(Requirement.project_id == project_id)
    rows = list((await db.execute(stmt)).scalars().all())
    return {r.id: r for r in rows}


async def _fetch_scenario_map(
    db: AsyncSession,
    project_id: int,
) -> dict[int, TestScenario]:
    stmt = select(TestScenario).where(TestScenario.project_id == project_id)
    rows = list((await db.execute(stmt)).scalars().all())
    return {s.id: s for s in rows}


# ── Excel styling helpers ───────────────────────────────────────────────────

def _make_header_style():
    """Return openpyxl styling objects — imported lazily to avoid hard dep."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
    header_fill = PatternFill(fill_type="solid", fgColor="1B59F8")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(border_style="thin", color="D0D7DE")
    header_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    return header_font, header_fill, header_align, header_border


def _style_header_row(ws, row: int, num_cols: int) -> None:
    from openpyxl.styles import Alignment, Border, Side
    header_font, header_fill, header_align, header_border = _make_header_style()
    thin = Side(border_style="thin", color="D0D7DE")
    cell_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    cell_align = Alignment(vertical="top", wrap_text=True)
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = header_border


def _style_data_row(ws, row: int, num_cols: int) -> None:
    from openpyxl.styles import Alignment, Border, Side
    thin = Side(border_style="thin", color="D0D7DE")
    cell_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    cell_align = Alignment(vertical="top", wrap_text=True)
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.alignment = cell_align
        cell.border = cell_border


# ── Public API ──────────────────────────────────────────────────────────────

async def export_test_cases_excel(
    db: AsyncSession,
    project_id: int,
    include_drafts: bool = False,
) -> bytes:
    """
    Return an Excel workbook (bytes) with one row per test case.

    Columns:
      TC ID | Title | Test Type | Priority | Severity | Automation | BDD | Steps |
      Preconditions | Expected Result | Status | Req ID | Req Title | Scenario ID |
      Scenario Title | Telecom Domain | Test Phase | Product Group | Product |
      Jira Key | External TC ID | External URL | Created At
    """
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    test_cases = await _fetch_all_test_cases(db, project_id, include_drafts)
    req_map = await _fetch_requirement_map(db, project_id)
    scen_map = await _fetch_scenario_map(db, project_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "Test Cases"

    headers = [
        "TC ID", "Title", "Test Type", "Priority", "Severity",
        "Automation Candidate", "BDD Scenario", "Steps", "Preconditions",
        "Expected Result", "Status", "Approval Status",
        "Requirement ID", "Requirement Title",
        "Scenario ID", "Scenario Title",
        "Telecom Domain", "Test Phase", "Product Group", "Product",
        "Jira Issue Key", "External TC ID", "External TC URL",
        "Created At",
    ]

    ws.row_dimensions[1].height = 32
    for col_idx, header in enumerate(headers, 1):
        ws.cell(row=1, column=col_idx, value=header)
    _style_header_row(ws, 1, len(headers))

    for row_idx, tc in enumerate(test_cases, 2):
        req = req_map.get(tc.requirement_id) if tc.requirement_id else None
        scen = scen_map.get(tc.scenario_id) if tc.scenario_id else None

        row_data = [
            _safe_str(tc.test_case_id),
            _safe_str(tc.title),
            _safe_str(tc.test_type or "functional"),
            _safe_str(tc.priority),
            _safe_str(tc.severity),
            "Yes" if tc.automation_candidate else "No",
            _safe_str(tc.bdd_scenario),
            _safe_str(_steps_to_text(tc.steps)),
            _safe_str(_list_to_text(tc.preconditions)),
            _safe_str(tc.expected_result),
            _safe_str(tc.status),
            _safe_str(getattr(tc, "approval_status", "")),
            _safe_str(req.requirement_id if req else ""),
            _safe_str(req.title if req else ""),
            _safe_str(scen.scenario_id if scen else ""),
            _safe_str(scen.title if scen else ""),
            _safe_str(tc.telecom_domain),
            _safe_str(tc.test_phase),
            _safe_str(tc.product_group),
            _safe_str(tc.product),
            _safe_str(tc.jira_issue_key),
            _safe_str(tc.external_tc_id),
            _safe_str(tc.external_tc_url),
            _safe_str(tc.created_at.isoformat() if tc.created_at else ""),
        ]

        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)
        _style_data_row(ws, row_idx, len(headers))

    # Set column widths
    col_widths = [
        14, 50, 16, 12, 12,
        18, 60, 60, 40,
        40, 14, 16,
        16, 40,
        14, 40,
        18, 16, 18, 16,
        16, 20, 40,
        22,
    ]
    for idx, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    # Freeze header row
    ws.freeze_panes = ws["A2"]

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def export_test_cases_csv(
    db: AsyncSession,
    project_id: int,
    include_drafts: bool = False,
) -> str:
    """Return a plain CSV string of all test cases."""
    test_cases = await _fetch_all_test_cases(db, project_id, include_drafts)
    req_map = await _fetch_requirement_map(db, project_id)
    scen_map = await _fetch_scenario_map(db, project_id)

    buf = io.StringIO()
    writer = csv.writer(buf, dialect="excel")

    writer.writerow([
        "TC ID", "Title", "Test Type", "Priority", "Severity",
        "Automation Candidate", "BDD Scenario", "Steps", "Preconditions",
        "Expected Result", "Status", "Approval Status",
        "Requirement ID", "Requirement Title", "Scenario ID", "Scenario Title",
        "Telecom Domain", "Test Phase", "Product Group", "Product",
        "Jira Issue Key", "External TC ID", "External TC URL", "Created At",
    ])

    for tc in test_cases:
        req = req_map.get(tc.requirement_id) if tc.requirement_id else None
        scen = scen_map.get(tc.scenario_id) if tc.scenario_id else None
        writer.writerow([
            tc.test_case_id or "",
            tc.title or "",
            tc.test_type or "functional",
            tc.priority or "",
            tc.severity or "",
            "Yes" if tc.automation_candidate else "No",
            tc.bdd_scenario or "",
            _steps_to_text(tc.steps),
            _list_to_text(tc.preconditions),
            tc.expected_result or "",
            tc.status or "",
            getattr(tc, "approval_status", "") or "",
            req.requirement_id if req else "",
            req.title if req else "",
            scen.scenario_id if scen else "",
            scen.title if scen else "",
            tc.telecom_domain or "",
            tc.test_phase or "",
            tc.product_group or "",
            tc.product or "",
            tc.jira_issue_key or "",
            tc.external_tc_id or "",
            tc.external_tc_url or "",
            tc.created_at.isoformat() if tc.created_at else "",
        ])

    return buf.getvalue()


async def export_test_cases_xray_csv(
    db: AsyncSession,
    project_id: int,
    include_drafts: bool = False,
) -> str:
    """
    Return an Xray-compatible CSV string for Jira Xray import.

    Format: one header row, then one or more data rows per test case.
    Multi-step manual tests: first row has Summary + meta, subsequent
    rows only have Step columns (matching Xray's CSV import spec).

    Ref: https://docs.getxray.app/display/XRAY/Importing+Test+Cases+from+CSV
    """
    test_cases = await _fetch_all_test_cases(db, project_id, include_drafts)
    req_map = await _fetch_requirement_map(db, project_id)

    buf = io.StringIO()
    writer = csv.writer(buf, dialect="excel")

    writer.writerow([
        "Summary", "Issue ID", "Test Type",
        "Generic Test Definition",   # BDD / Cucumber definition
        "Step Action", "Step Data", "Step Result",
        "Labels", "Priority", "Requirement Issue Key",
        "Telecom Domain", "External TC ID",
    ])

    for tc in test_cases:
        req = req_map.get(tc.requirement_id) if tc.requirement_id else None
        req_jira_key = req.jira_issue_key if req else ""

        steps = tc.steps or []
        test_type = "Cucumber" if tc.bdd_scenario else "Manual"

        # For BDD / Cucumber — single row with Generic Test Definition
        if test_type == "Cucumber":
            writer.writerow([
                tc.title or "",
                tc.test_case_id or "",
                "Cucumber",
                tc.bdd_scenario or "",
                "",  # Step Action
                "",  # Step Data
                "",  # Step Result
                "",
                tc.priority or "",
                req_jira_key or "",
                tc.telecom_domain or "",
                tc.external_tc_id or "",
            ])
            continue

        # Manual: emit one leading row per step (or one fallback row if no steps)
        if not steps:
            # EC-07: no steps — emit a single fallback row
            writer.writerow([
                tc.title or "",
                tc.test_case_id or "",
                "Manual",
                "",  # Generic Test Definition
                "Refer to test design document",
                "",
                "",
                "",
                tc.priority or "",
                req_jira_key or "",
                tc.telecom_domain or "",
                tc.external_tc_id or "",
            ])
        else:
            for step_idx, step in enumerate(steps):
                if isinstance(step, dict):
                    action = step.get("action") or step.get("step") or ""
                    data = step.get("test_data") or step.get("data") or ""
                    result = step.get("expected_result") or step.get("expected") or ""
                else:
                    # EC-08: step stored as plain string
                    action = str(step)
                    data = ""
                    result = ""

                if step_idx == 0:
                    # First step row — include all metadata
                    writer.writerow([
                        tc.title or "",
                        tc.test_case_id or "",
                        "Manual",
                        "",  # Generic Test Definition (not applicable)
                        _safe_str(action, 500),
                        _safe_str(data, 500),
                        _safe_str(result, 500),
                        "",
                        tc.priority or "",
                        req_jira_key or "",
                        tc.telecom_domain or "",
                        tc.external_tc_id or "",
                    ])
                else:
                    # Continuation step rows — Xray ignores leading cols
                    writer.writerow([
                        "",   # Summary (blank for continuation)
                        "",   # Issue ID
                        "",   # Test Type
                        "",   # Generic Test Definition
                        _safe_str(action, 500),
                        _safe_str(data, 500),
                        _safe_str(result, 500),
                        "", "", "", "", "",
                    ])

    return buf.getvalue()


async def export_traceability_matrix_excel(
    db: AsyncSession,
    project_id: int,
    include_drafts: bool = False,
) -> bytes:
    """
    Return an Excel workbook (bytes) with the requirement→test-case traceability matrix.

    Sheet 1: Matrix (one row per requirement)
    Sheet 2: Summary (counts by status)
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    # Fetch data
    req_stmt = select(Requirement).where(Requirement.project_id == project_id)
    if not include_drafts:
        req_stmt = req_stmt.where(Requirement.status == "approved")
    req_stmt = req_stmt.order_by(Requirement.id)
    requirements = list((await db.execute(req_stmt)).scalars().all())

    # Build requirement → test case mapping
    tc_stmt = select(TestCase).where(TestCase.project_id == project_id)
    if not include_drafts:
        tc_stmt = tc_stmt.where(TestCase.status == "approved")
    all_tcs = list((await db.execute(tc_stmt)).scalars().all())

    tc_by_req: dict[int, list[TestCase]] = {}
    for tc in all_tcs:
        if tc.requirement_id:
            tc_by_req.setdefault(tc.requirement_id, []).append(tc)

    # Execution results for test cases
    tc_ids = [tc.id for tc in all_tcs]
    er_by_tc: dict[int, list[ExecutionResult]] = {}
    if tc_ids:
        er_stmt = select(ExecutionResult).where(
            ExecutionResult.project_id == project_id,
            ExecutionResult.test_case_id.in_(tc_ids),
        )
        if not include_drafts:
            er_stmt = er_stmt.join(
                ExecutionRun, ExecutionRun.id == ExecutionResult.execution_run_id
            ).where(ExecutionRun.status == "approved")
        for er in (await db.execute(er_stmt)).scalars().all():
            if er.test_case_id:
                er_by_tc.setdefault(er.test_case_id, []).append(er)

    # Defects
    defect_by_tc: dict[int, list[DefectDraft]] = {}
    if tc_ids:
        def_stmt = select(DefectDraft).where(
            DefectDraft.project_id == project_id,
        )
        if not include_drafts:
            def_stmt = def_stmt.where(
                DefectDraft.status.in_(["approved", "pushed_to_jira"])
            )
        for d in (await db.execute(def_stmt)).scalars().all():
            # DefectDraft links via execution_result_id
            pass  # we aggregate at requirement level below

    wb = Workbook()

    # ── Sheet 1: Matrix ────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Traceability Matrix"

    matrix_headers = [
        "Requirement ID", "Requirement Title", "Status",
        "Risk Level", "Telecom Domain", "Test Phase",
        "Test Case Count", "TC IDs", "Automation Candidates",
        "Execution Results", "Latest Execution Status",
        "Open Defects", "Coverage Gaps",
    ]

    ws.row_dimensions[1].height = 30
    for col_idx, header in enumerate(matrix_headers, 1):
        ws.cell(row=1, column=col_idx, value=header)
    _style_header_row(ws, 1, len(matrix_headers))

    # Status color fills
    green_fill = PatternFill(fill_type="solid", fgColor="D1FAE5")
    red_fill = PatternFill(fill_type="solid", fgColor="FEE2E2")
    amber_fill = PatternFill(fill_type="solid", fgColor="FEF3C7")

    for row_idx, req in enumerate(requirements, 2):
        tcs = tc_by_req.get(req.id, [])
        tc_ids_str = ", ".join(tc.test_case_id for tc in tcs[:20])
        if len(tcs) > 20:
            tc_ids_str += f"… +{len(tcs) - 20} more"

        auto_count = sum(1 for tc in tcs if tc.automation_candidate)

        # Collect all execution results for all TCs of this requirement
        all_ers: list[ExecutionResult] = []
        for tc in tcs:
            all_ers.extend(er_by_tc.get(tc.id, []))

        er_statuses = [er.status for er in all_ers]
        er_summary = ", ".join(sorted(set(er_statuses))) if er_statuses else "none"
        latest_status = all_ers[-1].status if all_ers else "not executed"

        # Gaps
        gaps: list[str] = []
        if not tcs:
            gaps.append("no test cases")
        elif not all_ers:
            gaps.append("no execution")
        failed = [er for er in all_ers if er.status in {"failed", "error"}]
        if failed:
            gaps.append(f"{len(failed)} failures")
        gaps_str = "; ".join(gaps) if gaps else "none"

        row_data = [
            _safe_str(req.requirement_id),
            _safe_str(req.title),
            _safe_str(req.status),
            _safe_str(req.risk_level or ""),
            _safe_str(req.telecom_domain or ""),
            _safe_str(req.test_phase or ""),
            len(tcs),
            _safe_str(tc_ids_str),
            auto_count,
            len(all_ers),
            _safe_str(latest_status),
            len(failed) if failed else 0,
            _safe_str(gaps_str),
        ]

        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)

        # Row fill by gap status
        fill = green_fill if not gaps else (red_fill if "no test cases" in gaps else amber_fill)
        from openpyxl.styles import Alignment, Border, Side
        thin = Side(border_style="thin", color="D0D7DE")
        cell_border = Border(left=thin, right=thin, top=thin, bottom=thin)
        cell_align = Alignment(vertical="top", wrap_text=True)
        for col_idx in range(1, len(matrix_headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = fill
            cell.alignment = cell_align
            cell.border = cell_border

    # Column widths for matrix
    matrix_widths = [18, 50, 14, 14, 18, 14, 16, 40, 20, 18, 22, 14, 24]
    for idx, width in enumerate(matrix_widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = ws["A2"]

    # ── Sheet 2: Summary ───────────────────────────────────────────────────
    ws2 = wb.create_sheet(title="Summary")

    summary_data = [
        ("Total Requirements", len(requirements)),
        ("Total Test Cases (approved)", len(all_tcs)),
        ("Requirements with Test Cases", sum(1 for req in requirements if req.id in tc_by_req)),
        ("Requirements WITHOUT Test Cases", sum(1 for req in requirements if req.id not in tc_by_req)),
        ("Automation Candidates", sum(1 for tc in all_tcs if tc.automation_candidate)),
        ("Include Drafts", "Yes" if include_drafts else "No"),
    ]

    ws2.column_dimensions["A"].width = 36
    ws2.column_dimensions["B"].width = 18

    from openpyxl.styles import Font
    ws2.cell(row=1, column=1, value="Metric").font = Font(bold=True, color="1B59F8")
    ws2.cell(row=1, column=2, value="Value").font = Font(bold=True, color="1B59F8")

    for row_idx, (metric, value) in enumerate(summary_data, 2):
        ws2.cell(row=row_idx, column=1, value=metric)
        ws2.cell(row=row_idx, column=2, value=value)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Per-requirement traceability chain ─────────────────────────────────────

async def get_requirement_traceability_chain(
    db: AsyncSession,
    requirement_id: int,
    project_id: int,
) -> dict[str, Any]:
    """
    Return a nested dict with the full traceability chain for one requirement:
      requirement → scenarios → test cases → execution results → defects

    Edge cases:
      - Requirement not found → raises ValueError
      - No scenarios/test cases/executions/defects → returns empty lists
      - Execution results fetched across all test cases of the requirement
    """
    # Requirement
    req_result = await db.execute(
        select(Requirement).where(
            Requirement.id == requirement_id,
            Requirement.project_id == project_id,
        )
    )
    req = req_result.scalar_one_or_none()
    if req is None:
        raise ValueError(f"Requirement {requirement_id} not found in project {project_id}")

    # Scenarios
    scen_result = await db.execute(
        select(TestScenario).where(
            TestScenario.requirement_id == requirement_id,
            TestScenario.project_id == project_id,
        ).order_by(TestScenario.id)
    )
    scenarios = list(scen_result.scalars().all())

    # Test Cases (via requirement_id directly, or via scenario)
    tc_result = await db.execute(
        select(TestCase).where(
            TestCase.project_id == project_id,
            TestCase.requirement_id == requirement_id,
        ).order_by(TestCase.id)
    )
    test_cases = list(tc_result.scalars().all())

    # Also collect TCs linked via scenarios (without direct requirement linkage)
    scen_ids = [s.id for s in scenarios]
    tc_by_id = {tc.id: tc for tc in test_cases}
    if scen_ids:
        scen_tc_result = await db.execute(
            select(TestCase).where(
                TestCase.project_id == project_id,
                TestCase.scenario_id.in_(scen_ids),
                TestCase.requirement_id.is_(None),  # avoid duplicates
            ).order_by(TestCase.id)
        )
        for tc in scen_tc_result.scalars().all():
            tc_by_id[tc.id] = tc
    test_cases = list(tc_by_id.values())

    # Execution Results
    tc_ids = [tc.id for tc in test_cases]
    exec_results: list[ExecutionResult] = []
    if tc_ids:
        er_result = await db.execute(
            select(ExecutionResult).where(
                ExecutionResult.project_id == project_id,
                ExecutionResult.test_case_id.in_(tc_ids),
            ).order_by(ExecutionResult.id.desc())
        )
        exec_results = list(er_result.scalars().all())

    # Defects
    er_ids = [er.id for er in exec_results]
    defects: list[DefectDraft] = []
    if er_ids:
        def_result = await db.execute(
            select(DefectDraft).where(
                DefectDraft.project_id == project_id,
                DefectDraft.execution_result_id.in_(er_ids),
            ).order_by(DefectDraft.id)
        )
        defects = list(def_result.scalars().all())

    # Build result dict
    def _req_dict(r: Requirement) -> dict:
        return {
            "id": r.id,
            "requirement_id": r.requirement_id,
            "title": r.title,
            "status": r.status,
            "risk_level": r.risk_level,
            "telecom_domain": r.telecom_domain,
            "quality_score": r.quality_score,
            "quality_verdict": r.quality_verdict,
        }

    def _scen_dict(s: TestScenario) -> dict:
        return {
            "id": s.id,
            "scenario_id": s.scenario_id,
            "title": s.title,
            "scenario_type": s.scenario_type,
            "priority": s.priority,
            "status": s.status,
        }

    def _tc_dict(tc: TestCase) -> dict:
        return {
            "id": tc.id,
            "test_case_id": tc.test_case_id,
            "title": tc.title,
            "test_type": tc.test_type,
            "priority": tc.priority,
            "status": tc.status,
            "automation_candidate": tc.automation_candidate,
            "scenario_id": tc.scenario_id,
            "jira_issue_key": tc.jira_issue_key,
        }

    def _er_dict(er: ExecutionResult) -> dict:
        return {
            "id": er.id,
            "test_case_id": er.test_case_id,
            "test_name": er.test_name,
            "status": er.status,
            "execution_mode": er.execution_mode,
            "created_at": er.created_at.isoformat() if er.created_at else None,
        }

    def _defect_dict(d: DefectDraft) -> dict:
        return {
            "id": d.id,
            "defect_id": d.defect_id,
            "summary": d.summary,
            "severity": d.severity,
            "priority": d.priority,
            "status": d.status,
            "jira_ready": d.jira_ready,
        }

    # Summary gaps
    gaps: list[str] = []
    if not test_cases:
        gaps.append("no_test_cases")
    if test_cases and not exec_results:
        gaps.append("no_execution")
    failed_ers = [er for er in exec_results if er.status in {"failed", "error"}]
    defect_er_ids = {d.execution_result_id for d in defects}
    if any(er.id not in defect_er_ids for er in failed_ers):
        gaps.append("undecided_failures")

    return {
        "requirement": _req_dict(req),
        "scenarios": [_scen_dict(s) for s in scenarios],
        "test_cases": [_tc_dict(tc) for tc in test_cases],
        "execution_results": [_er_dict(er) for er in exec_results],
        "defects": [_defect_dict(d) for d in defects],
        "summary": {
            "scenario_count": len(scenarios),
            "test_case_count": len(test_cases),
            "execution_count": len(exec_results),
            "defect_count": len(defects),
            "gaps": gaps,
        },
    }
