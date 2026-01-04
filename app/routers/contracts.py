"""Router for Contracts entity with special handling for renewals."""

import logging

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

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
    ValidationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contracts", tags=["Contracts"])


@router.get("/template")
async def download_template() -> Response:
    """Download CSV template for contracts."""
    template_content = generate_template("contracts")
    return Response(
        content=template_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="contracts_template.csv"'
        },
    )


@router.get("/fields")
async def get_fields() -> dict:
    """Get field information for contracts."""
    all_fields = get_all_fields("contracts")
    required_fields = get_required_fields("contracts")
    return {
        "fields": all_fields,
        "required_fields": required_fields,
    }


@router.post("/validate")
async def validate_csv(file: UploadFile = File(...)) -> ValidationResponse:
    """Validate CSV file for contracts."""
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)
    return validate_csv_data("contracts", rows)


def group_rows_by_person(
    rows: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """
    Group rows by resource_id or candidate_id and sort by start_date.

    This ensures contracts for the same person are processed together,
    with the oldest contract first (initial) and subsequent ones as renewals.
    """
    groups: dict[str, list[dict[str, str]]] = {}

    for row in rows:
        resource_id = row.get("resource_id", "").strip()
        candidate_id = row.get("candidate_id", "").strip()

        # Create a unique key for the person
        if resource_id:
            key = f"resource:{resource_id}"
        elif candidate_id:
            key = f"candidate:{candidate_id}"
        else:
            key = f"unknown:{id(row)}"

        if key not in groups:
            groups[key] = []
        groups[key].append(row)

    # Sort each group by start_date (oldest first = initial contract)
    for key in groups:
        groups[key].sort(key=lambda r: r.get("start_date", "") or "9999-99-99")

    return groups


@router.post("/import")
async def import_csv(file: UploadFile = File(...)) -> ImportResponse:
    """
    Import CSV file into BoondManager with automatic renewal handling.

    Contracts are grouped by resource_id/candidate_id and sorted by start_date.
    For each person:
    - The first contract (oldest start_date) = initial contract
    - Subsequent contracts = renewals linked to the previous one

    If parent_contract_id is already specified in CSV, it takes precedence.
    """
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    # Validate first
    validation = validate_csv_data("contracts", rows)
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

    # Group rows by person for renewal linking
    person_groups = group_rows_by_person(rows)

    # Track created contracts for renewal linking
    # Key: (person_key, row_index) -> contract_id
    created_contracts: dict[tuple[str, int], str] = {}
    # Key: person_key -> last_contract_id (for automatic renewal chaining)
    last_contract_by_person: dict[str, str] = {}

    # Import each row
    client = get_boond_client()
    results: list[ImportResult] = []
    success_count = 0
    failed_count = 0

    # Create a mapping of original row index
    row_to_index: dict[int, int] = {id(row): idx + 1 for idx, row in enumerate(rows)}

    # Process each person's contracts in order (sorted by start_date)
    for person_key, person_rows in person_groups.items():
        is_first_for_person = True

        for row in person_rows:
            row_num = row_to_index[id(row)]
            converted_row = convert_row_values(row, "contracts")

            # Determine if this is a renewal
            parent_contract_id = converted_row.get("parent_contract_id")
            result_message = None

            if parent_contract_id:
                # Manual linking from CSV - use as-is
                result_message = f"Renouvellement (parent: {parent_contract_id})"
            elif not is_first_for_person and person_key in last_contract_by_person:
                # Auto-link as renewal of previous contract for same resource
                converted_row["parent_contract_id"] = int(
                    last_contract_by_person[person_key]
                )
                result_message = f"Renouvellement auto (parent: {last_contract_by_person[person_key]})"
                logger.info(
                    f"Row {row_num}: Auto-linking as renewal of contract "
                    f"{last_contract_by_person[person_key]} for {person_key}"
                )
            else:
                # First contract for this person
                result_message = "Contrat initial"

            success, entity_id, error_msg = await client.create_entity(
                "contracts", converted_row
            )

            if success:
                success_count += 1
                results.append(
                    ImportResult(
                        row=row_num,
                        status="success",
                        id=entity_id,
                        message=result_message,
                        original_data=row,
                    )
                )
                logger.info(f"Row {row_num}: Created contract with ID {entity_id} ({result_message})")

                # Store for potential renewal linking
                created_contracts[(person_key, row_num)] = entity_id
                last_contract_by_person[person_key] = entity_id
                is_first_for_person = False
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
                logger.warning(
                    f"Row {row_num}: Failed to create contract: {error_msg}"
                )

    # Sort results by row number for consistent output
    results.sort(key=lambda r: r.row)

    return ImportResponse(
        total=len(rows),
        success=success_count,
        failed=failed_count,
        results=results,
    )
