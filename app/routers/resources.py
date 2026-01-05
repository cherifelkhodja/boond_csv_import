"""Router for Resources entity - update type and provider."""

import logging

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from app.boond_client import get_boond_client
from app.csv_parser import parse_csv
from app.models import ImportResponse, ImportResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resources", tags=["Resources"])

# CSV columns (informational columns not used by code are marked)
# Required: resource_id
# Optional: resource_type_id, resource_company_id
# Informational only: Référence interne, resource_surname, resource_name,
#                     resource_type, resource_company_name


@router.get("/template")
async def download_template() -> Response:
    """Download CSV template for resources update."""
    template_content = (
        "resource_id,resource_type_id,resource_company_id,"
        "resource_surname,resource_name,resource_type,resource_company_name\n"
        "123,1,456,DUPONT,Jean,Salarié,ACME Corp\n"
    )
    return Response(
        content=template_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="resources_template.csv"'
        },
    )


@router.get("/fields")
async def get_fields() -> dict:
    """Get field information for resources update."""
    return {
        "fields": [
            {"name": "resource_id", "required": True, "description": "Resource ID to update"},
            {"name": "resource_type_id", "required": False, "description": "New type ID for the resource"},
            {"name": "resource_company_id", "required": False, "description": "Provider company ID"},
            {"name": "resource_surname", "required": False, "description": "Informational - not used"},
            {"name": "resource_name", "required": False, "description": "Informational - not used"},
            {"name": "resource_type", "required": False, "description": "Informational - not used"},
            {"name": "resource_company_name", "required": False, "description": "Informational - not used"},
        ],
        "required_fields": ["resource_id"],
    }


@router.post("/validate")
async def validate_csv(file: UploadFile = File(...)) -> dict:
    """Validate CSV file for resources update."""
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    errors = []
    for idx, row in enumerate(rows, start=1):
        resource_id = row.get("resource_id", "").strip()
        if not resource_id:
            errors.append({
                "row": idx,
                "field": "resource_id",
                "error": "resource_id is required",
            })

    return {
        "valid": len(errors) == 0,
        "total_rows": len(rows),
        "errors": errors,
    }


@router.post("/import")
async def import_csv(file: UploadFile = File(...)) -> ImportResponse:
    """
    Import CSV file to update resources in BoondManager.

    Workflow for each row:
    1. Update resource type (PUT /resources/{id}/information) if resource_type_id provided
    2. If resource_company_id is empty, stop processing this row
    3. Get first contact of the company (GET /companies/{id}/contacts)
    4. If no contact found, warn and stop processing this row
    5. Update provider (PUT /resources/{id}/administrative) with company and contact
    """
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    _, rows = parse_csv(text_content)

    # Validate first
    errors = []
    for idx, row in enumerate(rows, start=1):
        resource_id = row.get("resource_id", "").strip()
        if not resource_id:
            errors.append({
                "row": idx,
                "field": "resource_id",
                "error": "resource_id is required",
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

    # Process each row
    client = get_boond_client()
    results: list[ImportResult] = []
    success_count = 0
    failed_count = 0

    for idx, row in enumerate(rows, start=1):
        resource_id = row.get("resource_id", "").strip()
        resource_type_id = row.get("resource_type_id", "").strip()
        resource_company_id = row.get("resource_company_id", "").strip()

        messages: list[str] = []
        has_error = False

        # Step 1: Update resource type if provided
        if resource_type_id:
            try:
                type_id = int(resource_type_id)
                success, error_msg = await client.update_resource_type(resource_id, type_id)
                if success:
                    messages.append(f"Type mis à jour: {type_id}")
                else:
                    messages.append(f"Erreur type: {error_msg}")
                    has_error = True
            except ValueError:
                messages.append(f"resource_type_id invalide: {resource_type_id}")
                has_error = True
        else:
            messages.append("Type: non modifié (vide)")

        # Step 2: Check if company_id is provided
        if not resource_company_id:
            messages.append("Société: non modifiée (vide)")
        else:
            # Step 3: Get first contact of the company
            contact_success, contact_id, contact_error = await client.get_company_first_contact(
                resource_company_id
            )

            if not contact_success:
                messages.append(f"Erreur récupération contacts: {contact_error}")
                has_error = True
            elif not contact_id:
                # Step 4: No contact found - warn and skip provider update
                messages.append(f"⚠️ Aucun contact trouvé pour société {resource_company_id}")
            else:
                # Step 5: Update provider company and contact
                provider_success, provider_error = await client.update_resource_provider(
                    resource_id, resource_company_id, contact_id
                )
                if provider_success:
                    messages.append(f"Société: {resource_company_id}, Contact: {contact_id}")
                else:
                    messages.append(f"Erreur société: {provider_error}")
                    has_error = True

        # Record result
        status = "error" if has_error else "success"
        if status == "success":
            success_count += 1
        else:
            failed_count += 1

        results.append(
            ImportResult(
                row=idx,
                status=status,
                id=resource_id,
                message=" | ".join(messages),
                original_data=row,
            )
        )
        logger.info(f"Row {idx}: Resource {resource_id} - {' | '.join(messages)}")

    return ImportResponse(
        total=len(rows),
        success=success_count,
        failed=failed_count,
        results=results,
    )
