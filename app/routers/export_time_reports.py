"""Router for exporting time reports from BoondManager."""

import asyncio
import json
import logging
from io import StringIO

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from app.boond_client import get_boond_client
from app.csv_parser import parse_csv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/export-time-reports", tags=["Export Time Reports"])

# Default delay between API calls (ms)
DEFAULT_API_DELAY_MS = 100


def _extract_time_entries(
    time_report_data: dict,
    resource_id: str,
) -> list[dict]:
    """
    Extract time entries (regular and exceptional) from a time-report detail.

    Args:
        time_report_data: Full time-report response with data, included
        resource_id: The resource ID for the export

    Returns: List of CSV row dicts
    """
    entries = []
    data = time_report_data.get("data", {})
    attributes = data.get("attributes", {})
    relationships = data.get("relationships", {})
    included = time_report_data.get("included", [])

    term = attributes.get("term", "")

    # Build lookup for included items (projects, deliveries, companies)
    included_by_type_id = {}
    for item in included:
        item_type = item.get("type")
        item_id = item.get("id")
        if item_type and item_id:
            included_by_type_id[(item_type, item_id)] = item

    # Get agency_id from relationships
    agency_data = relationships.get("agency", {}).get("data", {})
    agency_id = agency_data.get("id", "") if agency_data else ""

    # Process regularTimes
    regular_times = attributes.get("regularTimes", [])
    for reg in regular_times:
        start_date = reg.get("startDate", "")
        duration = reg.get("duration", 0)
        row_id = reg.get("row", "")

        # Extract workUnitType info
        work_unit_type = reg.get("workUnitType", {})
        wut_reference = work_unit_type.get("reference", "")
        wut_name = work_unit_type.get("name", "")
        wut_activity_type = work_unit_type.get("activityType", "")

        # Extract relationships
        project_data = reg.get("project", {})
        project_id = project_data.get("id", "") if project_data else ""

        delivery_data = reg.get("delivery", {})
        delivery_id = delivery_data.get("id", "") if delivery_data else ""

        batch_data = reg.get("batch", {})
        batch_id = batch_data.get("id", "") if batch_data else ""

        # Get company_id from project in included
        company_id = ""
        if project_id:
            project_included = included_by_type_id.get(("project", project_id))
            if project_included:
                company_rel = project_included.get("relationships", {}).get("company", {}).get("data", {})
                company_id = company_rel.get("id", "") if company_rel else ""

        entries.append({
            "type": "regular",
            "term": term,
            "startDate": start_date,
            "endDate": "",
            "duration": duration,
            "row": row_id,
            "description": "",
            "recovering": "",
            "workUnitType_reference": wut_reference,
            "workUnitType_name": wut_name,
            "workUnitType_activityType": wut_activity_type,
            "project_id": project_id,
            "delivery_id": delivery_id,
            "batch_id": batch_id,
            "resource_id": resource_id,
            "agency_id": agency_id,
            "company_id": company_id,
        })

    # Process exceptionalTimes
    exceptional_times = attributes.get("exceptionalTimes", [])
    for exc in exceptional_times:
        start_date = exc.get("startDate", "")
        end_date = exc.get("endDate", "")
        duration = exc.get("duration", 0)
        description = exc.get("description", "")
        recovering = exc.get("recovering", "")

        # Extract workUnitType info
        work_unit_type = exc.get("workUnitType", {})
        wut_reference = work_unit_type.get("reference", "")
        wut_name = work_unit_type.get("name", "")
        wut_activity_type = work_unit_type.get("activityType", "")

        # Extract relationships
        project_data = exc.get("project", {})
        project_id = project_data.get("id", "") if project_data else ""

        delivery_data = exc.get("delivery", {})
        delivery_id = delivery_data.get("id", "") if delivery_data else ""

        batch_data = exc.get("batch", {})
        batch_id = batch_data.get("id", "") if batch_data else ""

        # Get company_id from project in included
        company_id = ""
        if project_id:
            project_included = included_by_type_id.get(("project", project_id))
            if project_included:
                company_rel = project_included.get("relationships", {}).get("company", {}).get("data", {})
                company_id = company_rel.get("id", "") if company_rel else ""

        entries.append({
            "type": "exceptional",
            "term": term,
            "startDate": start_date,
            "endDate": end_date,
            "duration": duration,
            "row": "",
            "description": description,
            "recovering": str(recovering).lower() if recovering is not None else "",
            "workUnitType_reference": wut_reference,
            "workUnitType_name": wut_name,
            "workUnitType_activityType": wut_activity_type,
            "project_id": project_id,
            "delivery_id": delivery_id,
            "batch_id": batch_id,
            "resource_id": resource_id,
            "agency_id": agency_id,
            "company_id": company_id,
        })

    return entries


def _generate_csv_content(entries: list[dict]) -> str:
    """Generate CSV content from time entries."""
    if not entries:
        return ""

    headers = [
        "type", "term", "startDate", "endDate", "duration", "row", "description",
        "recovering", "workUnitType_reference", "workUnitType_name", "workUnitType_activityType",
        "project_id", "delivery_id", "batch_id", "resource_id", "agency_id", "company_id"
    ]

    lines = [",".join(headers)]

    for entry in entries:
        row_values = []
        for h in headers:
            value = entry.get(h, "")
            # Escape values containing comma or quotes
            value_str = str(value) if value is not None else ""
            if "," in value_str or '"' in value_str or "\n" in value_str:
                value_str = f'"{value_str.replace(chr(34), chr(34)+chr(34))}"'
            row_values.append(value_str)
        lines.append(",".join(row_values))

    return "\n".join(lines)


@router.post("/export")
async def export_time_reports(
    file: UploadFile = File(...),
    api_delay_ms: int = DEFAULT_API_DELAY_MS,
) -> StreamingResponse:
    """
    Export all time reports for resources from a CSV file.
    Returns Server-Sent Events for real-time progress.

    The CSV file should contain a `resource_id` column.
    """
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    # Extract resource_ids from CSV
    resource_ids = []
    for row in rows:
        resource_id = row.get("resource_id")
        if resource_id:
            resource_ids.append(str(resource_id))

    async def generate_events():
        client = get_boond_client()
        all_entries: list[dict] = []
        total_resources = len(resource_ids)
        success_count = 0
        failed_count = 0
        current = 0

        for resource_id in resource_ids:
            current += 1

            # Send progress event
            progress_event = {
                "type": "progress",
                "current": current,
                "total": total_resources,
                "action": f"Traitement resource {resource_id}...",
                "percent": int((current / total_resources) * 100) if total_resources > 0 else 0,
            }
            yield f"data: {json.dumps(progress_event)}\n\n"

            # Send action event
            yield f"data: {json.dumps({'type': 'action', 'message': f'GET /resources/{resource_id}/times-reports'})}\n\n"

            # Get times-reports for resource
            success, times_reports, error = await client.get_resource_times_reports(resource_id)

            if not success:
                yield f"data: {json.dumps({'type': 'action', 'message': f'ERROR Resource {resource_id}: {error}'})}\n\n"
                failed_count += 1
                continue

            if not times_reports:
                yield f"data: {json.dumps({'type': 'action', 'message': f'Resource {resource_id}: Aucun time-report'})}\n\n"
                success_count += 1
                continue

            # Get details for each time-report
            resource_entries = []
            for tr in times_reports:
                tr_id = tr.get("id")
                if not tr_id:
                    continue

                # Delay between API calls
                if api_delay_ms > 0:
                    await asyncio.sleep(api_delay_ms / 1000.0)

                yield f"data: {json.dumps({'type': 'action', 'message': f'GET /times-reports/{tr_id}'})}\n\n"

                detail_success, detail_data, detail_error = await client.get_time_report_detail(tr_id)

                if detail_success and detail_data:
                    entries = _extract_time_entries(detail_data, resource_id)
                    resource_entries.extend(entries)
                else:
                    yield f"data: {json.dumps({'type': 'action', 'message': f'ERROR Time-report {tr_id}: {detail_error}'})}\n\n"

            all_entries.extend(resource_entries)
            yield f"data: {json.dumps({'type': 'action', 'message': f'Resource {resource_id}: {len(resource_entries)} entrees exportees'})}\n\n"
            success_count += 1

            # Delay between resources
            if api_delay_ms > 0:
                await asyncio.sleep(api_delay_ms / 1000.0)

        # Generate CSV content
        csv_content = _generate_csv_content(all_entries)

        # Send final result
        final_result = {
            "type": "complete",
            "total": total_resources,
            "success": success_count,
            "failed": failed_count,
            "total_entries": len(all_entries),
            "csv_content": csv_content,
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
