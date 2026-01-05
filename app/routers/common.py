"""Common router logic for all entity types."""

import logging
from typing import Callable

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


def create_entity_router(entity_type: str) -> APIRouter:
    """Create a router for a specific entity type."""
    router = APIRouter(prefix=f"/{entity_type}", tags=[entity_type.capitalize()])

    @router.get("/template")
    async def download_template() -> Response:
        """Download CSV template for this entity type."""
        template_content = generate_template(entity_type)
        return Response(
            content=template_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{entity_type}_template.csv"'
            },
        )

    @router.get("/fields")
    async def get_fields() -> dict:
        """Get field information for this entity type."""
        all_fields = get_all_fields(entity_type)
        required_fields = get_required_fields(entity_type)
        return {
            "fields": all_fields,
            "required_fields": required_fields,
        }

    @router.post("/validate")
    async def validate_csv(file: UploadFile = File(...)) -> ValidationResponse:
        """Validate CSV file for this entity type."""
        content = await file.read()
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            text_content = content.decode("latin-1")

        _, rows = parse_csv(text_content)
        return validate_csv_data(entity_type, rows)

    @router.post("/import")
    async def import_csv(file: UploadFile = File(...)) -> ImportResponse:
        """Import CSV file into BoondManager."""
        content = await file.read()
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            text_content = content.decode("latin-1")

        _, rows = parse_csv(text_content)

        # Validate first
        validation = validate_csv_data(entity_type, rows)
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

        for row_num, row in enumerate(rows, start=1):
            converted_row = convert_row_values(row, entity_type)
            success, entity_id, error_msg = await client.create_entity(
                entity_type, converted_row
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
                logger.info(f"Row {row_num}: Created {entity_type} with ID {entity_id}")
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
                logger.warning(f"Row {row_num}: Failed to create {entity_type}: {error_msg}")

        return ImportResponse(
            total=len(rows),
            success=success_count,
            failed=failed_count,
            results=results,
        )

    return router
