"""CSV parsing and validation utilities."""

import csv
import io
import logging
import re
from typing import Any

from app.models import (
    ENTITY_CONFIGS,
    ValidationError,
    ValidationResponse,
)

logger = logging.getLogger(__name__)

# Date format regex (YYYY-MM-DD)
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Boolean values
TRUE_VALUES = {"true", "1", "yes", "oui"}
FALSE_VALUES = {"false", "0", "no", "non"}


def detect_delimiter(content: str) -> str:
    """Detect CSV delimiter (comma or semicolon)."""
    first_line = content.split('\n')[0] if content else ''
    semicolons = first_line.count(';')
    commas = first_line.count(',')
    return ';' if semicolons > commas else ','


def parse_csv(content: str) -> tuple[list[str], list[dict[str, str]]]:
    """
    Parse CSV content into headers and rows.
    Automatically detects delimiter (comma or semicolon).

    Returns: (headers, list of row dicts)
    """
    delimiter = detect_delimiter(content)
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    headers = reader.fieldnames or []
    rows = list(reader)
    return headers, rows


def get_required_fields(entity_type: str) -> list[str]:
    """Get list of required field names for an entity type."""
    config = ENTITY_CONFIGS.get(entity_type)
    if not config:
        return []
    return [field for field, (_, required, _, _) in config["fields"].items() if required]


def get_all_fields(entity_type: str) -> list[str]:
    """Get list of all field names for an entity type."""
    config = ENTITY_CONFIGS.get(entity_type)
    if not config:
        return []
    return list(config["fields"].keys())


def validate_value(
    value: str,
    field_name: str,
    entity_type: str,
) -> str | None:
    """
    Validate a single value.

    Returns: Error message if invalid, None if valid.
    """
    if not value or value.strip() == "":
        return None  # Empty values are handled by required field check

    value = value.strip()

    # Check for date fields
    if field_name in ("start_date", "end_date", "date"):
        if not DATE_REGEX.match(value):
            return "Format de date invalide (attendu: YYYY-MM-DD)"

    # Check for numeric fields (IDs)
    if field_name.endswith("_id") or field_name == "delivery_ids":
        if field_name == "delivery_ids":
            # Can be comma-separated
            for part in value.split(","):
                if not part.strip().isdigit():
                    return "ID invalide (doit être un entier)"
        else:
            if not value.isdigit():
                return "ID invalide (doit être un entier)"

    # Check for boolean fields
    boolean_fields = {
        "show_order_number", "show_project_reference", "show_resource_name",
        "show_working_days", "show_daily_prices", "show_bank_details",
        "show_vat_number", "show_factor", "show_footer", "show_comments",
        "separate_times_expenses", "separate_exceptional_activities",
        "group_mission", "group_expenses", "copy_comments",
        "attach_signed_timesheets", "attach_unsigned_timesheets",
        "attach_expenses", "request_timesheets_signature",
        "merge_invoice_attachments", "rebillable",
    }
    if field_name in boolean_fields:
        if value.lower() not in TRUE_VALUES | FALSE_VALUES:
            return "Valeur booléenne invalide (attendu: true/false)"

    # Check for decimal fields
    decimal_fields = {
        "exchange_rate", "work_unit_rate", "additional_turnover",
        "additional_investment", "remains_to_be_done", "signed_turnover",
        "average_daily_price_excluding_tax", "purchase_price_excluding_tax",
        "turnover_excluding_tax", "turnover_including_tax", "tax_rate",
        "amount_excluding_tax", "amount_including_tax", "rebillable_rate",
    }
    if field_name in decimal_fields:
        try:
            float(value)
        except ValueError:
            return "Valeur numérique invalide"

    return None


def validate_csv_data(
    entity_type: str,
    rows: list[dict[str, str]],
) -> ValidationResponse:
    """
    Validate CSV data for an entity type.

    Returns: ValidationResponse with validation results.
    """
    config = ENTITY_CONFIGS.get(entity_type)
    if not config:
        return ValidationResponse(
            valid=False,
            total_rows=len(rows),
            errors=[ValidationError(row=0, field="", error=f"Type d'entité inconnu: {entity_type}")],
        )

    required_fields = get_required_fields(entity_type)
    errors: list[ValidationError] = []

    for row_num, row in enumerate(rows, start=1):
        # Check required fields
        for field in required_fields:
            value = row.get(field, "").strip()
            if not value:
                errors.append(
                    ValidationError(
                        row=row_num,
                        field=field,
                        error="Champ requis manquant",
                    )
                )

        # Validate all provided fields
        for field, value in row.items():
            if not value or not value.strip():
                continue

            error_msg = validate_value(value, field, entity_type)
            if error_msg:
                errors.append(
                    ValidationError(
                        row=row_num,
                        field=field,
                        error=error_msg,
                    )
                )

    return ValidationResponse(
        valid=len(errors) == 0,
        total_rows=len(rows),
        errors=errors,
    )


def convert_row_values(
    row: dict[str, str],
    entity_type: str,
) -> dict[str, Any]:
    """
    Convert string values to appropriate Python types.

    Returns: dict with converted values.
    """
    config = ENTITY_CONFIGS.get(entity_type)
    if not config:
        return row

    converted: dict[str, Any] = {}

    for field, value in row.items():
        if not value or value.strip() == "":
            continue

        value = value.strip()

        # Boolean conversion
        boolean_fields = {
            "show_order_number", "show_project_reference", "show_resource_name",
            "show_working_days", "show_daily_prices", "show_bank_details",
            "show_vat_number", "show_factor", "show_footer", "show_comments",
            "separate_times_expenses", "separate_exceptional_activities",
            "group_mission", "group_expenses", "copy_comments",
            "attach_signed_timesheets", "attach_unsigned_timesheets",
            "attach_expenses", "request_timesheets_signature",
            "merge_invoice_attachments", "rebillable", "force_average_daily_price",
        }
        if field in boolean_fields:
            converted[field] = value.lower() in TRUE_VALUES
            continue

        # Decimal conversion
        decimal_fields = {
            "exchange_rate", "work_unit_rate", "additional_turnover",
            "additional_investment", "remains_to_be_done", "signed_turnover",
            "average_daily_price_excluding_tax", "purchase_price_excluding_tax",
            "turnover_excluding_tax", "turnover_including_tax", "tax_rate",
            "amount_excluding_tax", "amount_including_tax", "rebillable_rate",
            "number_of_days_invoiced", "number_of_days_free", "work_unit_rate", "exchange_rate",
        }
        if field in decimal_fields:
            try:
                converted[field] = float(value)
            except ValueError:
                converted[field] = value
            continue

        # Integer conversion for IDs (except delivery_ids which is a string list)
        if field.endswith("_id") and field != "delivery_ids":
            try:
                converted[field] = int(value)
            except ValueError:
                converted[field] = value
            continue

        # Integer conversion for type/state/mode fields
        integer_fields = {
            "type_of", "state", "mode", "billing_mode", "billing_type",
            "payment_terms", "payment_method", "language",
        }
        if field in integer_fields:
            try:
                converted[field] = int(value)
            except ValueError:
                converted[field] = value
            continue

        # Keep as string
        converted[field] = value

    return converted


def generate_template(entity_type: str) -> str:
    """Generate CSV template for an entity type."""
    config = ENTITY_CONFIGS.get(entity_type)
    if config and "template_fields" in config:
        fields = config["template_fields"]
    else:
        fields = get_all_fields(entity_type)
    return ",".join(fields)
