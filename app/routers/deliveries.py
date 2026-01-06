"""Router for Deliveries entity with contract end date update logic."""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.boond_client import get_boond_client
from app.csv_parser import (
    convert_row_values,
    generate_template,
    get_all_fields,
    get_required_fields,
    parse_csv,
    validate_csv_data,
)
from app.models import (
    ImportResponse,
    ImportResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deliveries", tags=["Deliveries"])

# Cutoff date for contract updates
CUTOFF_DATE = date(2025, 12, 31)


@router.get("/template")
async def download_template() -> Response:
    """Download CSV template for deliveries."""
    template_content = generate_template("deliveries")
    return Response(
        content=template_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="deliveries_template.csv"'
        },
    )


@router.get("/fields")
async def get_fields() -> dict:
    """Get field information for deliveries."""
    all_fields = get_all_fields("deliveries")
    required_fields = get_required_fields("deliveries")
    return {
        "fields": all_fields,
        "required_fields": required_fields,
    }


@router.post("/validate")
async def validate_csv(file: UploadFile = File(...)) -> dict:
    """Validate CSV file for deliveries."""
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)
    return validate_csv_data("deliveries", rows)


@router.post("/import")
async def import_csv(file: UploadFile = File(...)) -> ImportResponse:
    """Import CSV file into BoondManager with contract end date updates."""
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    # Validate first
    validation = validate_csv_data("deliveries", rows)
    if not validation.valid:
        return ImportResponse(
            total=validation.total_rows,
            success=0,
            failed=validation.total_rows,
            results=[
                ImportResult(
                    row=error.row,
                    status="error",
                    id=None,
                    message=f"{error.field}: {error.error}",
                )
                for error in validation.errors
            ],
        )

    # Import each row
    client = get_boond_client()
    results: list[ImportResult] = []
    success_count = 0
    failed_count = 0

    # Track successful deliveries for contract update logic
    successful_deliveries: list[dict] = []

    for row_num, row in enumerate(rows, start=1):
        converted_row = convert_row_values(row, "deliveries")
        success, entity_id, error_msg = await client.create_entity(
            "deliveries", converted_row
        )

        if success:
            success_count += 1
            results.append(
                ImportResult(
                    row=row_num,
                    status="success",
                    id=entity_id,
                    message=None,
                    original_data=row,
                )
            )
            logger.info(f"Row {row_num}: Created delivery with ID {entity_id}")

            # Track for contract update
            successful_deliveries.append({
                "row_num": row_num,
                "delivery_id": entity_id,
                "project_id": row.get("project_id"),
                "resource_id": row.get("resource_id"),
                "end_date": row.get("end_date"),
            })
        else:
            failed_count += 1
            results.append(
                ImportResult(
                    row=row_num,
                    status="error",
                    id=None,
                    message=error_msg,
                    original_data=row,
                )
            )
            logger.warning(f"Row {row_num}: Failed to create delivery: {error_msg}")

    # After import: update contracts for last deliveries per project
    contract_updates = await _update_contracts_for_last_deliveries(
        client, successful_deliveries, results
    )

    # Add contract update info to results
    for update in contract_updates:
        # Find the corresponding result and add message
        for result in results:
            if result.row == update["row_num"]:
                if update["success"]:
                    if result.message:
                        result.message += f" | Contrat {update['contract_id']} mis à jour"
                    else:
                        result.message = f"Contrat {update['contract_id']} mis à jour (endDate={update['end_date']}, endReason=4)"
                else:
                    if result.message:
                        result.message += f" | Warning: {update['error']}"
                    else:
                        result.message = f"Warning: {update['error']}"
                break

    return ImportResponse(
        total=len(rows),
        success=success_count,
        failed=failed_count,
        results=results,
    )


async def _update_contracts_for_last_deliveries(
    client,
    successful_deliveries: list[dict],
    results: list[ImportResult],
) -> list[dict]:
    """
    Update contracts for the last delivery of each project.

    Logic:
    1. Group deliveries by project_id
    2. For each project, find the delivery with the latest end_date
    3. If end_date > today AND end_date < 31/12/2025:
       - Get the resource's contracts
       - Find the contract with most recent startDate
       - Update that contract with endDate and endReason=4
    """
    contract_updates = []

    # Group deliveries by project_id
    deliveries_by_project: dict[str, list[dict]] = defaultdict(list)
    for delivery in successful_deliveries:
        project_id = delivery.get("project_id")
        if project_id:
            deliveries_by_project[project_id].append(delivery)

    # Process each project
    for project_id, deliveries in deliveries_by_project.items():
        # Find the delivery with the latest end_date
        last_delivery = _find_last_delivery(deliveries)
        if not last_delivery:
            continue

        end_date_str = last_delivery.get("end_date")
        if not end_date_str:
            continue

        # Parse end_date
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            try:
                end_date = datetime.strptime(end_date_str, "%d/%m/%Y").date()
            except ValueError:
                logger.warning(f"Invalid end_date format: {end_date_str}")
                continue

        # Check condition: end_date < 31/12/2025
        if not (end_date < CUTOFF_DATE):
            logger.info(
                f"Project {project_id}: end_date {end_date} >= cutoff {CUTOFF_DATE}, "
                f"skipping contract update"
            )
            continue

        resource_id = last_delivery.get("resource_id")
        if not resource_id:
            continue

        # Get resource's contracts with details
        success, contracts, error = await client.get_resource_contracts_with_details(
            resource_id
        )

        if not success:
            contract_updates.append({
                "row_num": last_delivery["row_num"],
                "success": False,
                "error": f"Impossible de récupérer les contrats: {error}",
            })
            continue

        if not contracts:
            contract_updates.append({
                "row_num": last_delivery["row_num"],
                "success": False,
                "error": "Aucun contrat trouvé pour cette ressource",
            })
            continue

        # Find contract with most recent startDate
        latest_contract = _find_latest_contract(contracts)
        if not latest_contract:
            contract_updates.append({
                "row_num": last_delivery["row_num"],
                "success": False,
                "error": "Aucun contrat avec startDate trouvé",
            })
            continue

        # Update the contract
        contract_id = latest_contract["id"]
        end_date_formatted = end_date.strftime("%Y-%m-%d")

        success, error = await client.update_contract(
            contract_id, end_date_formatted, end_reason=4
        )

        if success:
            contract_updates.append({
                "row_num": last_delivery["row_num"],
                "success": True,
                "contract_id": contract_id,
                "end_date": end_date_formatted,
            })
            logger.info(
                f"Updated contract {contract_id} for resource {resource_id} "
                f"with endDate={end_date_formatted}, endReason=4"
            )
        else:
            contract_updates.append({
                "row_num": last_delivery["row_num"],
                "success": False,
                "error": f"Échec mise à jour contrat {contract_id}: {error}",
            })

    return contract_updates


def _find_last_delivery(deliveries: list[dict]) -> dict | None:
    """Find the delivery with the latest end_date."""
    if not deliveries:
        return None

    def parse_date(date_str: str | None) -> date | None:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            try:
                return datetime.strptime(date_str, "%d/%m/%Y").date()
            except ValueError:
                return None

    # Sort by end_date descending
    sorted_deliveries = sorted(
        deliveries,
        key=lambda d: parse_date(d.get("end_date")) or date.min,
        reverse=True,
    )

    return sorted_deliveries[0] if sorted_deliveries else None


def _find_latest_contract(contracts: list[dict]) -> dict | None:
    """Find the contract with the most recent startDate."""
    if not contracts:
        return None

    def parse_date(date_str: str | None) -> date | None:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return None

    # Filter contracts with startDate and sort by startDate descending
    contracts_with_start = [c for c in contracts if c.get("startDate")]
    if not contracts_with_start:
        return None

    sorted_contracts = sorted(
        contracts_with_start,
        key=lambda c: parse_date(c.get("startDate")) or date.min,
        reverse=True,
    )

    return sorted_contracts[0] if sorted_contracts else None


@router.post("/update-positionings")
async def update_positionings(file: UploadFile = File(...)) -> StreamingResponse:
    """
    Update positioning updateDate based on first delivery per project/resource.
    Returns Server-Sent Events for real-time progress.
    """
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    # Group by (project_id, resource_id)
    deliveries_by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row_num, row in enumerate(rows, start=1):
        project_id = row.get("project_id")
        resource_id = row.get("resource_id")
        if project_id and resource_id:
            deliveries_by_pair[(project_id, resource_id)].append({
                "row_num": row_num,
                "start_date": row.get("start_date"),
                "original_data": row,
            })

    async def generate_events():
        client = get_boond_client()
        results: list[dict] = []
        success_count = 0
        failed_count = 0
        total_pairs = len(deliveries_by_pair)
        current = 0

        for (project_id, resource_id), deliveries in deliveries_by_pair.items():
            current += 1

            # Find first delivery by start_date
            first_delivery = _find_first_delivery(deliveries)
            if not first_delivery:
                continue

            start_date_str = first_delivery.get("start_date")

            # Send progress event
            progress_event = {
                "type": "progress",
                "current": current,
                "total": total_pairs,
                "action": f"Traitement projet {project_id}, ressource {resource_id}...",
                "percent": int((current / total_pairs) * 100),
            }
            yield f"data: {json.dumps(progress_event)}\n\n"

            if not start_date_str:
                results.append({
                    "row": first_delivery["row_num"],
                    "status": "error",
                    "id": None,
                    "message": "Pas de start_date",
                })
                failed_count += 1
                continue

            # Parse and format start_date
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            except ValueError:
                try:
                    start_date = datetime.strptime(start_date_str, "%d/%m/%Y").date()
                except ValueError:
                    results.append({
                        "row": first_delivery["row_num"],
                        "status": "error",
                        "id": None,
                        "message": f"Format de date invalide: {start_date_str}",
                    })
                    failed_count += 1
                    continue

            # Format as datetime with timezone (e.g., 2026-01-05T12:23:25+0100)
            paris_tz = timezone(timedelta(hours=1))
            update_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=paris_tz)
            update_date_formatted = update_datetime.strftime("%Y-%m-%dT%H:%M:%S%z")

            # Send action event
            yield f"data: {json.dumps({'type': 'action', 'message': f'GET /projects/{project_id}'})}\n\n"

            # Get project's opportunity
            success, project_data, error = await client.get_project(project_id)
            if not success or not project_data:
                results.append({
                    "row": first_delivery["row_num"],
                    "status": "error",
                    "id": None,
                    "message": f"Impossible de récupérer le projet {project_id}: {error}",
                })
                failed_count += 1
                continue

            # Extract opportunity_id from project relationships
            opportunity_id = (
                project_data.get("relationships", {})
                .get("opportunity", {})
                .get("data", {})
                .get("id")
            )

            if not opportunity_id:
                results.append({
                    "row": first_delivery["row_num"],
                    "status": "error",
                    "id": None,
                    "message": f"Pas d'opportunité liée au projet {project_id}",
                })
                failed_count += 1
                continue

            # Send action event
            yield f"data: {json.dumps({'type': 'action', 'message': f'GET /resources/{resource_id}/positionings'})}\n\n"

            # Get resource's positionings
            success, positionings, error = await client.get_resource_positionings(resource_id)
            if not success:
                results.append({
                    "row": first_delivery["row_num"],
                    "status": "error",
                    "id": None,
                    "message": f"Impossible de récupérer les positionnements: {error}",
                })
                failed_count += 1
                continue

            # Find positioning matching the opportunity
            matching_positioning = None
            for pos in positionings:
                pos_opportunity_id = (
                    pos.get("relationships", {})
                    .get("opportunity", {})
                    .get("data", {})
                    .get("id")
                )
                if pos_opportunity_id == opportunity_id:
                    matching_positioning = pos
                    break

            if not matching_positioning:
                results.append({
                    "row": first_delivery["row_num"],
                    "status": "warning",
                    "id": None,
                    "message": f"Pas de positionnement trouvé pour l'opportunité {opportunity_id}",
                })
                failed_count += 1
                continue

            positioning_id = matching_positioning.get("id")

            # Send action event
            yield f"data: {json.dumps({'type': 'action', 'message': f'PUT /positionings/{positioning_id}'})}\n\n"

            # Update the positioning
            success, error = await client.update_positioning(positioning_id, update_date_formatted)

            if success:
                results.append({
                    "row": first_delivery["row_num"],
                    "status": "success",
                    "id": positioning_id,
                    "message": f"Positionnement {positioning_id} mis à jour (updateDate={update_date_formatted})",
                })
                success_count += 1
                logger.info(
                    f"Updated positioning {positioning_id} for project {project_id}, "
                    f"resource {resource_id} with updateDate={update_date_formatted}"
                )
            else:
                results.append({
                    "row": first_delivery["row_num"],
                    "status": "error",
                    "id": None,
                    "message": f"Échec mise à jour positionnement: {error}",
                })
                failed_count += 1

        # Send final result
        final_result = {
            "type": "complete",
            "total": total_pairs,
            "success": success_count,
            "failed": failed_count,
            "results": results,
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


def _find_first_delivery(deliveries: list[dict]) -> dict | None:
    """Find the delivery with the earliest start_date."""
    if not deliveries:
        return None

    def parse_date(date_str: str | None) -> date | None:
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            try:
                return datetime.strptime(date_str, "%d/%m/%Y").date()
            except ValueError:
                return None

    # Sort by start_date ascending (earliest first)
    sorted_deliveries = sorted(
        deliveries,
        key=lambda d: parse_date(d.get("start_date")) or date.max,
    )

    return sorted_deliveries[0] if sorted_deliveries else None
