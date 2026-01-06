"""Router for importing time reports to BoondManager."""

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from app.boond_client import get_boond_client
from app.csv_parser import parse_csv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import-time-reports", tags=["Import Time Reports"])

# Default delay between API calls (ms)
DEFAULT_API_DELAY_MS = 100


def _build_regular_time_entry(row: dict) -> dict:
    """Build a regular time entry from a CSV row."""
    entry = {
        "startDate": row.get("startDate", ""),
        "duration": float(row.get("duration", 0) or 0),
        "row": int(row.get("row", 0) or 0),
    }

    # Add workUnitType
    wut_reference = row.get("workUnitType_reference", "")
    if wut_reference:
        entry["workUnitType"] = {"reference": wut_reference}

    # Add project relationship if present
    project_id = row.get("project_id", "")
    if project_id:
        entry["project"] = {"id": str(project_id)}

    # Add delivery relationship if present
    delivery_id = row.get("delivery_id", "")
    if delivery_id:
        entry["delivery"] = {"id": str(delivery_id)}

    # Add batch relationship if present
    batch_id = row.get("batch_id", "")
    if batch_id:
        entry["batch"] = {"id": str(batch_id)}

    return entry


def _build_exceptional_time_entry(row: dict) -> dict:
    """Build an exceptional time entry from a CSV row."""
    entry = {
        "startDate": row.get("startDate", ""),
        "endDate": row.get("endDate", "") or row.get("startDate", ""),
        "duration": float(row.get("duration", 0) or 0),
        "description": row.get("description", ""),
    }

    # Handle recovering field
    recovering = row.get("recovering", "")
    if recovering.lower() == "true":
        entry["recovering"] = True
    elif recovering.lower() == "false":
        entry["recovering"] = False

    # Add workUnitType
    wut_reference = row.get("workUnitType_reference", "")
    if wut_reference:
        entry["workUnitType"] = {"reference": wut_reference}

    # Add project relationship if present
    project_id = row.get("project_id", "")
    if project_id:
        entry["project"] = {"id": str(project_id)}

    # Add delivery relationship if present
    delivery_id = row.get("delivery_id", "")
    if delivery_id:
        entry["delivery"] = {"id": str(delivery_id)}

    # Add batch relationship if present
    batch_id = row.get("batch_id", "")
    if batch_id:
        entry["batch"] = {"id": str(batch_id)}

    return entry


def _group_entries_by_resource_term(rows: list[dict]) -> dict:
    """
    Group CSV rows by (resource_id, term) to create time-reports.

    Returns: {(resource_id, term): {"regular": [...], "exceptional": [...]}}
    """
    grouped = defaultdict(lambda: {"regular": [], "exceptional": []})

    for row in rows:
        resource_id = row.get("resource_id", "")
        term = row.get("term", "")
        entry_type = row.get("type", "regular")

        if not resource_id or not term:
            continue

        key = (resource_id, term)

        if entry_type == "exceptional":
            entry = _build_exceptional_time_entry(row)
            grouped[key]["exceptional"].append(entry)
        else:
            entry = _build_regular_time_entry(row)
            grouped[key]["regular"].append(entry)

    return grouped


@router.post("/import")
async def import_time_reports(
    file: UploadFile = File(...),
    api_delay_ms: int = DEFAULT_API_DELAY_MS,
) -> StreamingResponse:
    """
    Import time reports from a CSV file.
    Returns Server-Sent Events for real-time progress.

    The CSV file should have columns matching the export format:
    type, term, startDate, endDate, duration, row, description, recovering,
    workUnitType_reference, workUnitType_name, workUnitType_activityType,
    project_id, delivery_id, batch_id, resource_id, agency_id, company_id
    """
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    # Group entries by resource_id and term
    grouped = _group_entries_by_resource_term(rows)
    total_reports = len(grouped)

    async def generate_events():
        client = get_boond_client()
        success_count = 0
        failed_count = 0
        current = 0
        total_entries_imported = 0

        for (resource_id, term), entries in grouped.items():
            current += 1

            # Send progress event
            progress_event = {
                "type": "progress",
                "current": current,
                "total": total_reports,
                "action": f"Import resource {resource_id} - {term}...",
                "percent": int((current / total_reports) * 100) if total_reports > 0 else 0,
            }
            yield f"data: {json.dumps(progress_event)}\n\n"

            regular_times = entries["regular"] if entries["regular"] else None
            exceptional_times = entries["exceptional"] if entries["exceptional"] else None

            entries_count = len(entries["regular"]) + len(entries["exceptional"])

            yield f"data: {json.dumps({'type': 'action', 'message': f'POST /times-reports (resource={resource_id}, term={term}, {entries_count} entries)'})}\n\n"

            success, time_report_id, error = await client.create_time_report(
                resource_id=resource_id,
                term=term,
                regular_times=regular_times,
                exceptional_times=exceptional_times,
            )

            if success:
                yield f"data: {json.dumps({'type': 'action', 'message': f'Resource {resource_id} - {term}: time-report {time_report_id} cree ({entries_count} entrees)'})}\n\n"
                success_count += 1
                total_entries_imported += entries_count
            else:
                yield f"data: {json.dumps({'type': 'action', 'message': f'ERROR Resource {resource_id} - {term}: {error}'})}\n\n"
                failed_count += 1

            # Delay between API calls
            if api_delay_ms > 0:
                await asyncio.sleep(api_delay_ms / 1000.0)

        # Send final result
        final_result = {
            "type": "complete",
            "total": total_reports,
            "success": success_count,
            "failed": failed_count,
            "total_entries": total_entries_imported,
        }
        yield f"data: {json.dumps(final_result)}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
