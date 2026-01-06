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

# Fixed values for import
FIXED_WORK_UNIT_TYPE_REFERENCE = "1"
FIXED_DURATION = 1


def _build_regular_time_entry(row: dict) -> dict:
    """Build a regular time entry from a CSV row with fixed values."""
    # Handle case-insensitive column names
    start_date = row.get("startDate") or row.get("startdate") or row.get("StartDate") or ""
    project_id = row.get("project_id") or row.get("Project_id") or row.get("PROJECT_ID") or ""
    delivery_id = row.get("delivery_id") or row.get("Delivery_id") or row.get("DELIVERY_ID") or ""

    entry = {
        "startDate": start_date,
        "duration": FIXED_DURATION,
        "row": -1,
        "workUnitType": {"reference": FIXED_WORK_UNIT_TYPE_REFERENCE},
        "batch": None,
    }

    # Add project if provided
    if project_id:
        entry["project"] = {"id": str(project_id)}

    # Add delivery if provided
    if delivery_id:
        entry["delivery"] = {"id": str(delivery_id)}

    logger.info(f"Built entry: {entry}")

    return entry


def _group_entries_by_resource_term(rows: list[dict]) -> dict:
    """
    Group CSV rows by (resource_id, term) to create time-reports.

    Returns: {(resource_id, term): [entry1, entry2, ...]}
    """
    grouped = defaultdict(list)

    for row in rows:
        # Handle case-insensitive column names
        resource_id = row.get("resource_id") or row.get("Resource_id") or row.get("RESOURCE_ID") or ""
        term = row.get("term") or row.get("Term") or row.get("TERM") or ""

        if not resource_id or not term:
            logger.warning(f"Skipping row with missing resource_id or term: {row}")
            continue

        key = (resource_id, term)
        entry = _build_regular_time_entry(row)
        grouped[key].append(entry)

    logger.info(f"Grouped {len(grouped)} time-reports from {len(rows)} rows")

    return grouped


@router.post("/import")
async def import_time_reports(
    file: UploadFile = File(...),
    api_delay_ms: int = DEFAULT_API_DELAY_MS,
) -> StreamingResponse:
    """
    Import time reports from a CSV file.
    Returns Server-Sent Events for real-time progress.

    The CSV file should have columns:
    - resource_id (required)
    - term (required, YYYY-MM format)
    - startDate (required, YYYY-MM-DD format)

    Fixed values applied:
    - type: regular
    - duration: 1
    - workUnitType_reference: 1
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

            entries_count = len(entries)

            yield f"data: {json.dumps({'type': 'action', 'message': f'POST /times-reports (resource={resource_id}, term={term}, {entries_count} entries)'})}\n\n"

            success, time_report_id, error = await client.create_time_report(
                resource_id=resource_id,
                term=term,
                regular_times=entries,
                exceptional_times=None,
            )

            if success:
                yield f"data: {json.dumps({'type': 'action', 'message': f'Resource {resource_id} - {term}: time-report {time_report_id} cree ({entries_count} entrees)'})}\n\n"

                # Validate the time-report
                yield f"data: {json.dumps({'type': 'action', 'message': f'POST /times-reports/{time_report_id}/validate'})}\n\n"
                validate_success, validate_error = await client.validate_time_report(time_report_id)

                if validate_success:
                    yield f"data: {json.dumps({'type': 'action', 'message': f'Resource {resource_id} - {term}: time-report {time_report_id} valide'})}\n\n"
                    success_count += 1
                    total_entries_imported += entries_count
                else:
                    yield f"data: {json.dumps({'type': 'action', 'message': f'ERROR Resource {resource_id} - {term}: validation echouee - {validate_error}'})}\n\n"
                    failed_count += 1
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
