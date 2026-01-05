"""Router for Resource Contracts - create contracts for resources."""

import logging

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from app.boond_client import get_boond_client
from app.csv_parser import parse_csv
from app.models import ImportResponse, ImportResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resource-contracts", tags=["ResourceContracts"])


@router.get("/template")
async def download_template() -> Response:
    """Download CSV template for resource contracts."""
    template_content = (
        "resource_id,resource_name,resource_type,contract_typeOf,contract_start_date,"
        "contract_end_date,contract_monthly_salary,contract_daily_production_cost,contract_renewal\n"
        "123,DUPONT Jean,Salarié,0,2024-01-01,2024-12-31,3500,,FAUX\n"
        "456,MARTIN Paul,Externe,1,2024-01-01,2024-06-30,,450,FAUX\n"
    )
    return Response(
        content=template_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="resource_contracts_template.csv"'
        },
    )


@router.get("/fields")
async def get_fields() -> dict:
    """Get field information for resource contracts."""
    return {
        "fields": [
            {"name": "resource_id", "required": True, "description": "Resource ID (dependsOn)"},
            {"name": "contract_typeOf", "required": True, "description": "Contract type (0=salarié, 1=externe, etc.)"},
            {"name": "contract_start_date", "required": True, "description": "Start date (YYYY-MM-DD)"},
            {"name": "contract_end_date", "required": False, "description": "End date (YYYY-MM-DD)"},
            {"name": "contract_monthly_salary", "required": False, "description": "Monthly salary (if typeOf=0)"},
            {"name": "contract_daily_production_cost", "required": False, "description": "Daily cost (if typeOf!=0)"},
            {"name": "contract_renewal", "required": False, "description": "VRAI/FAUX - link to previous contract"},
            {"name": "resource_name", "required": False, "description": "Informational only"},
            {"name": "resource_type", "required": False, "description": "Informational only"},
        ],
        "required_fields": ["resource_id", "contract_typeOf", "contract_start_date"],
    }


@router.post("/validate")
async def validate_csv(file: UploadFile = File(...)) -> dict:
    """Validate CSV file for resource contracts."""
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    errors = []
    required_fields = ["resource_id", "contract_typeOf", "contract_start_date"]

    for idx, row in enumerate(rows, start=1):
        for field in required_fields:
            value = row.get(field, "").strip()
            if not value:
                errors.append({
                    "row": idx,
                    "field": field,
                    "error": f"{field} is required",
                })

    return {
        "valid": len(errors) == 0,
        "total_rows": len(rows),
        "errors": errors,
    }


def group_by_resource_and_sort(rows: list[dict]) -> dict[str, list[dict]]:
    """Group rows by resource_id and sort by start_date within each group."""
    groups: dict[str, list[dict]] = {}

    for row in rows:
        resource_id = row.get("resource_id", "").strip()
        if resource_id:
            if resource_id not in groups:
                groups[resource_id] = []
            groups[resource_id].append(row)

    # Sort each group by start_date
    for resource_id in groups:
        groups[resource_id].sort(
            key=lambda r: r.get("contract_start_date", "") or "9999-99-99"
        )

    return groups


@router.post("/import")
async def import_csv(file: UploadFile = File(...)) -> ImportResponse:
    """
    Import CSV file to create contracts for resources.

    Workflow:
    1. Group rows by resource_id and sort by start_date
    2. For each row, create a contract:
       - If typeOf=0: use monthly_salary
       - Else: use daily_production_cost
       - If contract_renewal=VRAI: link to previous contract (by start_date)
    """
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    # Validate first
    required_fields = ["resource_id", "contract_typeOf", "contract_start_date"]
    errors = []
    for idx, row in enumerate(rows, start=1):
        for field in required_fields:
            value = row.get(field, "").strip()
            if not value:
                errors.append({
                    "row": idx,
                    "field": field,
                    "error": f"{field} is required",
                })

    if errors:
        return ImportResponse(
            total=len(rows),
            success=0,
            failed=len(errors),
            results=[
                ImportResult(
                    row=e["row"],
                    status="error",
                    id=None,
                    message=f"{e['field']}: {e['error']}",
                )
                for e in errors
            ],
        )

    # Group by resource_id and sort by start_date
    resource_groups = group_by_resource_and_sort(rows)

    # Track original row numbers
    row_to_index: dict[int, int] = {id(row): idx + 1 for idx, row in enumerate(rows)}

    # Track created contracts per resource for renewal linking
    last_contract_by_resource: dict[str, str] = {}

    client = get_boond_client()
    results: list[ImportResult] = []
    success_count = 0
    failed_count = 0

    # Process each resource's contracts in order
    for resource_id, resource_rows in resource_groups.items():
        for row in resource_rows:
            row_num = row_to_index[id(row)]

            # Parse fields
            type_of = int(row.get("contract_typeOf", "0").strip() or "0")
            start_date = row.get("contract_start_date", "").strip()
            end_date = row.get("contract_end_date", "").strip()
            monthly_salary = row.get("contract_monthly_salary", "").strip()
            daily_cost = row.get("contract_daily_production_cost", "").strip()
            is_renewal = row.get("contract_renewal", "").strip().upper() == "VRAI"

            messages: list[str] = []

            # Determine parent contract for renewals
            parent_contract_id = None
            if is_renewal:
                if resource_id in last_contract_by_resource:
                    parent_contract_id = last_contract_by_resource[resource_id]
                    messages.append(f"Renouvellement (parent: {parent_contract_id})")
                else:
                    messages.append("⚠️ Renouvellement demandé mais pas de contrat précédent")

            # Create contract
            success, contract_id, error_msg = await client.create_resource_contract(
                resource_id=resource_id,
                type_of=type_of,
                start_date=start_date,
                end_date=end_date if end_date else None,
                monthly_salary=float(monthly_salary) if monthly_salary else None,
                daily_cost=float(daily_cost) if daily_cost else None,
                parent_contract_id=parent_contract_id,
            )

            if success:
                success_count += 1
                last_contract_by_resource[resource_id] = contract_id
                if not messages:
                    messages.append("Contrat initial")
                messages.append(f"Créé: {contract_id}")
                results.append(
                    ImportResult(
                        row=row_num,
                        status="success",
                        id=contract_id,
                        message=" | ".join(messages),
                        original_data=row,
                    )
                )
                logger.info(f"Row {row_num}: Created contract {contract_id} for resource {resource_id}")
            else:
                failed_count += 1
                results.append(
                    ImportResult(
                        row=row_num,
                        status="error",
                        id=None,
                        message=error_msg or "Unknown error",
                        original_data=row,
                    )
                )
                logger.warning(f"Row {row_num}: Failed to create contract: {error_msg}")

    # Sort results by row number
    results.sort(key=lambda r: r.row)

    return ImportResponse(
        total=len(rows),
        success=success_count,
        failed=failed_count,
        results=results,
    )


@router.post("/preview-delete")
async def preview_delete(file: UploadFile = File(...)) -> dict:
    """
    Preview deletion: count contracts that would be deleted for resources in CSV.
    Used for confirmation dialog before actual deletion.
    """
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    # Get unique resource_ids
    resource_ids = list(set(
        row.get("resource_id", "").strip()
        for row in rows
        if row.get("resource_id", "").strip()
    ))

    client = get_boond_client()
    total_contracts = 0
    resource_contract_counts: dict[str, int] = {}

    for resource_id in resource_ids:
        success, contract_ids, _ = await client.get_resource_contracts(resource_id)
        if success:
            resource_contract_counts[resource_id] = len(contract_ids)
            total_contracts += len(contract_ids)

    return {
        "total_resources": len(resource_ids),
        "total_contracts": total_contracts,
        "details": resource_contract_counts,
    }


@router.post("/delete-contracts")
async def delete_contracts(file: UploadFile = File(...)) -> ImportResponse:
    """
    Delete all contracts for resources listed in CSV.

    Workflow:
    1. Extract unique resource_ids from CSV
    2. For each resource, get their contracts via GET /resources/{id}/administrative
    3. Delete each contract via DELETE /contracts/{id}
    """
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    # Get unique resource_ids
    resource_ids = list(set(
        row.get("resource_id", "").strip()
        for row in rows
        if row.get("resource_id", "").strip()
    ))

    client = get_boond_client()
    results: list[ImportResult] = []
    success_count = 0
    failed_count = 0
    row_num = 0

    for resource_id in resource_ids:
        row_num += 1

        # Get contracts for this resource
        get_success, contract_ids, get_error = await client.get_resource_contracts(resource_id)

        if not get_success:
            failed_count += 1
            results.append(
                ImportResult(
                    row=row_num,
                    status="error",
                    id=resource_id,
                    message=f"Erreur récupération contrats: {get_error}",
                )
            )
            continue

        if not contract_ids:
            results.append(
                ImportResult(
                    row=row_num,
                    status="success",
                    id=resource_id,
                    message="Aucun contrat à supprimer",
                )
            )
            success_count += 1
            continue

        # Delete each contract
        deleted = 0
        errors = []
        for contract_id in contract_ids:
            del_success, del_error = await client.delete_contract(contract_id)
            if del_success:
                deleted += 1
            else:
                errors.append(f"CTR{contract_id}: {del_error}")

        if errors:
            failed_count += 1
            results.append(
                ImportResult(
                    row=row_num,
                    status="error",
                    id=resource_id,
                    message=f"Supprimés: {deleted}/{len(contract_ids)} | Erreurs: {'; '.join(errors)}",
                )
            )
        else:
            success_count += 1
            results.append(
                ImportResult(
                    row=row_num,
                    status="success",
                    id=resource_id,
                    message=f"Supprimés: {deleted} contrat(s)",
                )
            )

        logger.info(f"Resource {resource_id}: deleted {deleted}/{len(contract_ids)} contracts")

    return ImportResponse(
        total=len(resource_ids),
        success=success_count,
        failed=failed_count,
        results=results,
    )
