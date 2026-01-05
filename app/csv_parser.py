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


def parse_csv(content: str, entity_type: str | None = None) -> tuple[list[str], list[dict[str, str]]]:
    """
    Parse CSV content into headers and rows.
    Automatically detects delimiter (comma or semicolon).

    If entity_type is provided, filters out unknown columns and empty rows.

    Returns: (headers, list of row dicts)
    """
    delimiter = detect_delimiter(content)
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    headers = reader.fieldnames or []

    # Filter headers to only include known fields if entity_type is provided
    known_fields: set[str] = set()
    if entity_type:
        from app.models import ENTITY_CONFIGS
        config = ENTITY_CONFIGS.get(entity_type)
        if config:
            known_fields = set(config["fields"].keys())

    # Filter headers - keep only known fields (or all if no entity_type)
    if known_fields:
        filtered_headers = [h for h in headers if h in known_fields]
    else:
        filtered_headers = headers

    # Parse rows, filtering to only known columns
    rows = []
    for row in reader:
        if known_fields:
            # Only keep known fields
            filtered_row = {k: v for k, v in row.items() if k in known_fields}
        else:
            filtered_row = dict(row)

        # Skip completely empty rows
        if all(not v or not v.strip() for v in filtered_row.values()):
            continue

        rows.append(filtered_row)

    return filtered_headers, rows


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
        # Contract boolean fields
        "force_hourly_salary", "force_daily_cost",
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
        # Contract decimal fields
        "monthly_salary", "hourly_salary", "charge_factor",
        "daily_production_cost", "daily_expenses", "monthly_expenses",
        "hours_per_week", "activity_rate",
    }
    if field_name in decimal_fields:
        try:
            float(value)
        except ValueError:
            return "Valeur numérique invalide"

    # Contract-specific validations
    if field_name == "hours_per_week":
        hours = float(value)
        if hours < 0 or hours > 168:
            return "hours_per_week doit être entre 0 et 168"

    if field_name == "working_days":
        try:
            days = int(value)
            if days < 1 or days > 365:
                return "working_days doit être entre 1 et 365"
        except ValueError:
            return "working_days doit être un entier"

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

        # Contract-specific validation: resource_id OR candidate_id required
        if entity_type == "contracts":
            has_resource = bool(row.get("resource_id", "").strip())
            has_candidate = bool(row.get("candidate_id", "").strip())
            if not has_resource and not has_candidate:
                errors.append(
                    ValidationError(
                        row=row_num,
                        field="resource_id/candidate_id",
                        error="resource_id ou candidate_id obligatoire",
                    )
                )
            if has_resource and has_candidate:
                errors.append(
                    ValidationError(
                        row=row_num,
                        field="resource_id/candidate_id",
                        error="Renseigner resource_id OU candidate_id, pas les deux",
                    )
                )

            # Validate dates
            start_date = row.get("start_date", "").strip()
            end_date = row.get("end_date", "").strip()
            if start_date and end_date and start_date > end_date:
                errors.append(
                    ValidationError(
                        row=row_num,
                        field="end_date",
                        error="start_date doit être <= end_date",
                    )
                )

            probation_end_date = row.get("probation_end_date", "").strip()
            if probation_end_date and start_date and probation_end_date < start_date:
                errors.append(
                    ValidationError(
                        row=row_num,
                        field="probation_end_date",
                        error="probation_end_date doit être >= start_date",
                    )
                )

            # Validate force_daily_cost requires daily_production_cost
            force_daily_cost = row.get("force_daily_cost", "").strip().lower()
            daily_production_cost = row.get("daily_production_cost", "").strip()
            if force_daily_cost in TRUE_VALUES and not daily_production_cost:
                errors.append(
                    ValidationError(
                        row=row_num,
                        field="daily_production_cost",
                        error="daily_production_cost requis si force_daily_cost=true",
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
            # Contract boolean fields
            "force_hourly_salary", "force_daily_cost",
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
            "work_unit_rate", "exchange_rate",
            # Contract decimal fields
            "monthly_salary", "hourly_salary", "charge_factor",
            "daily_production_cost", "daily_expenses", "monthly_expenses",
            "hours_per_week", "activity_rate",
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
            "number_of_days_free", "number_of_days_invoiced",
            # Contract integer fields
            "employee_type", "working_time_type", "probation_state",
            "working_days", "currency",
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
