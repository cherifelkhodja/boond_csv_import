"""Router for importing provider invoices to BoondManager."""

import asyncio
import calendar
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from app.boond_client import get_boond_client
from app.csv_parser import parse_csv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/import-provider-invoices", tags=["Import Provider Invoices"])

# Default delay between API calls (ms)
DEFAULT_API_DELAY_MS = 100

# Provider invoices folder path
PROVIDER_INVOICES_FOLDER = Path(__file__).parent.parent.parent / "provider_invoices"

# French month names mapping
MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}


def _parse_french_month(month_name: str) -> int | None:
    """Parse French month name to month number (1-12)."""
    return MONTHS_FR.get(month_name.lower().strip())


def _parse_date_dmy(date_str: str) -> str | None:
    """Parse date from DD/MM/YYYY format to YYYY-MM-DD."""
    if not date_str:
        return None
    try:
        parts = date_str.strip().split("/")
        if len(parts) == 3:
            day, month, year = parts
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    except Exception:
        pass
    return None


def _calculate_dates(year: str, month_name: str, invoice_date: str = "") -> tuple[str, str, str]:
    """
    Calculate startDate, endDate and invoiceDate from year and month.

    Returns: (start_date, end_date, invoice_date) in YYYY-MM-DD format
    """
    month_num = _parse_french_month(month_name)
    if not month_num:
        return "", "", ""

    try:
        year_int = int(year)
        # First day of month
        start_date = f"{year_int}-{month_num:02d}-01"
        # Last day of month
        last_day = calendar.monthrange(year_int, month_num)[1]
        end_date = f"{year_int}-{month_num:02d}-{last_day:02d}"
        # Invoice date: use provided or default to end_date
        final_invoice_date = invoice_date.strip() if invoice_date.strip() else end_date
        return start_date, end_date, final_invoice_date
    except (ValueError, TypeError):
        return "", "", ""


def _find_purchase_for_resource(
    resource_id: str,
    start_date: str,
    purchases: list[dict],
) -> str | None:
    """
    Find purchase_id for a resource based on date range.

    Args:
        resource_id: The resource ID
        start_date: The invoice start date (YYYY-MM-DD)
        purchases: List of purchase records from CSV

    Returns: purchase_id if found, None otherwise
    """
    if not start_date:
        return None

    try:
        invoice_start = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        return None

    for purchase in purchases:
        # Get resource_id from purchase (case-insensitive)
        p_resource_id = (
            purchase.get("resource_id") or
            purchase.get("Resource_id") or
            purchase.get("RESOURCE_ID") or ""
        )

        if str(p_resource_id).strip() != str(resource_id).strip():
            continue

        # Get purchase dates (format: DD/MM/YYYY)
        p_start = purchase.get("starDate") or purchase.get("startDate") or purchase.get("start_date") or ""
        p_end = purchase.get("endDate") or purchase.get("end_date") or ""

        # Parse dates
        p_start_parsed = _parse_date_dmy(p_start)
        p_end_parsed = _parse_date_dmy(p_end)

        if not p_start_parsed or not p_end_parsed:
            continue

        try:
            purchase_start = datetime.strptime(p_start_parsed, "%Y-%m-%d")
            purchase_end = datetime.strptime(p_end_parsed, "%Y-%m-%d")

            # Check if invoice start is within purchase period
            if purchase_start <= invoice_start <= purchase_end:
                return purchase.get("purchase_id") or purchase.get("Purchase_id") or ""
        except ValueError:
            continue

    return None


def _check_file_exists(invoice_file: str) -> bool:
    """Check if the invoice file exists in the provider_invoices folder."""
    if not invoice_file:
        return False
    file_path = PROVIDER_INVOICES_FOLDER / invoice_file.strip()
    return file_path.exists()


def _parse_boolean(value: str) -> bool:
    """Parse boolean value from CSV (VRAI/FAUX, TRUE/FALSE, 1/0)."""
    if not value:
        return False
    val = value.strip().upper()
    return val in ("VRAI", "TRUE", "1", "OUI", "YES")


def _parse_amount(value: str) -> float:
    """Parse amount from CSV, handling comma as decimal separator."""
    if not value:
        return 0.0
    try:
        # Replace comma with dot for decimal
        return float(value.strip().replace(",", "."))
    except ValueError:
        return 0.0


def _process_invoice_row(
    row: dict,
    purchases: list[dict],
    row_num: int,
) -> dict:
    """
    Process a single invoice row and return preview data.

    Returns dict with all fields needed for preview and import.
    """
    # Extract fields (case-insensitive)
    invoice_year = row.get("invoice_year") or row.get("Invoice_year") or ""
    invoice_month = row.get("invoice_month") or row.get("Invoice_month") or ""
    invoice_date_raw = row.get("invoiceDate") or row.get("InvoiceDate") or ""
    resource_name = row.get("resource_name") or row.get("Resource_name") or ""
    resource_id = row.get("resource_id") or row.get("Resource_id") or ""
    reference = row.get("reference") or row.get("Reference") or ""
    amount_ht = row.get("amountExcludingTax") or row.get("AmountExcludingTax") or ""
    amount_ttc = row.get("amountIncludingTax") or row.get("AmountIncludingTax") or ""
    invoice_paid = row.get("invoice_paid") or row.get("Invoice_paid") or ""
    invoice_paid_date_raw = row.get("invoicePaid") or row.get("InvoicePaid") or ""
    invoice_missing = row.get("invoice_missing") or row.get("Invoice_missing") or ""
    invoice_file = row.get("invoice_file") or row.get("Invoice_file") or ""

    # Calculate dates
    start_date, end_date, invoice_date = _calculate_dates(invoice_year, invoice_month, invoice_date_raw)

    # Parse paid date (DD/MM/YYYY -> YYYY-MM-DD)
    paid_date = _parse_date_dmy(invoice_paid_date_raw)

    # Find purchase
    purchase_id = _find_purchase_for_resource(resource_id, start_date, purchases)

    # Parse amounts
    amount_excluding_tax = _parse_amount(amount_ht)
    amount_including_tax = _parse_amount(amount_ttc)

    # Parse booleans
    is_paid = _parse_boolean(invoice_paid)
    is_missing = _parse_boolean(invoice_missing)

    # Determine payment state
    payment_state = 2 if is_paid else 1

    # Check file status
    if is_missing:
        file_status = "na"  # N/A - invoice_missing = VRAI
    elif _check_file_exists(invoice_file):
        file_status = "found"
    else:
        file_status = "missing"

    # Determine overall status
    errors = []
    if not resource_id:
        errors.append("resource_id manquant")
    if not start_date or not end_date:
        errors.append("dates invalides")
    if not reference:
        errors.append("reference manquante")

    if errors:
        status = "error"
    elif not purchase_id or file_status == "missing":
        status = "partial"
    else:
        status = "ready"

    return {
        "row_num": row_num,
        "resource_name": resource_name,
        "resource_id": resource_id,
        "reference": reference,
        "invoice_year": invoice_year,
        "invoice_date": invoice_date,
        "start_date": start_date,
        "end_date": end_date,
        "amount_excluding_tax": amount_excluding_tax,
        "amount_including_tax": amount_including_tax,
        "purchase_id": purchase_id,
        "payment_state": payment_state,
        "paid_date": paid_date,
        "invoice_file": invoice_file,
        "file_status": file_status,
        "status": status,
        "errors": errors,
        "is_missing": is_missing,
    }


@router.post("/preview")
async def preview_provider_invoices(
    invoices_file: UploadFile = File(...),
    purchases_file: UploadFile = File(None),
) -> dict:
    """
    Preview provider invoices before import.

    Returns preview data with all rows and their status.
    """
    # Parse invoices CSV
    invoices_content = await invoices_file.read()
    try:
        invoices_text = invoices_content.decode("utf-8")
    except UnicodeDecodeError:
        invoices_text = invoices_content.decode("latin-1")

    _, invoice_rows = parse_csv(invoices_text)

    # Parse purchases CSV if provided
    purchases = []
    if purchases_file:
        purchases_content = await purchases_file.read()
        try:
            purchases_text = purchases_content.decode("utf-8")
        except UnicodeDecodeError:
            purchases_text = purchases_content.decode("latin-1")
        _, purchases = parse_csv(purchases_text)

    # Process each invoice row
    preview_rows = []
    for idx, row in enumerate(invoice_rows, start=1):
        processed = _process_invoice_row(row, purchases, idx)
        preview_rows.append(processed)

    # Calculate stats
    total = len(preview_rows)
    ready_count = sum(1 for r in preview_rows if r["status"] == "ready")
    partial_count = sum(1 for r in preview_rows if r["status"] == "partial")
    error_count = sum(1 for r in preview_rows if r["status"] == "error")
    with_payment = sum(1 for r in preview_rows if r["purchase_id"])
    with_document = sum(1 for r in preview_rows if r["file_status"] == "found")

    return {
        "rows": preview_rows,
        "stats": {
            "total": total,
            "ready": ready_count,
            "partial": partial_count,
            "error": error_count,
            "with_payment": with_payment,
            "with_document": with_document,
        }
    }


@router.post("/import")
async def import_provider_invoices(
    invoices_file: UploadFile = File(...),
    purchases_file: UploadFile = File(None),
    api_delay_ms: int = DEFAULT_API_DELAY_MS,
) -> StreamingResponse:
    """
    Import provider invoices from CSV.
    Returns Server-Sent Events for real-time progress.
    """
    # Parse invoices CSV
    invoices_content = await invoices_file.read()
    try:
        invoices_text = invoices_content.decode("utf-8")
    except UnicodeDecodeError:
        invoices_text = invoices_content.decode("latin-1")

    _, invoice_rows = parse_csv(invoices_text)

    # Parse purchases CSV if provided
    purchases = []
    if purchases_file:
        purchases_content = await purchases_file.read()
        try:
            purchases_text = purchases_content.decode("utf-8")
        except UnicodeDecodeError:
            purchases_text = purchases_content.decode("latin-1")
        _, purchases = parse_csv(purchases_text)

    # Process rows for import
    processed_rows = []
    for idx, row in enumerate(invoice_rows, start=1):
        processed = _process_invoice_row(row, purchases, idx)
        processed_rows.append(processed)

    total = len(processed_rows)

    async def generate_events():
        client = get_boond_client()

        # Counters
        invoices_created = 0
        payments_added = 0
        documents_attached = 0
        without_purchase = 0
        without_document = 0
        errors = 0

        # Results for CSV export
        results = []

        for idx, row in enumerate(processed_rows, start=1):
            row_num = row["row_num"]
            reference = row["reference"]
            resource_name = row["resource_name"]
            resource_id = row["resource_id"]

            # Progress event
            progress_event = {
                "type": "progress",
                "current": idx,
                "total": total,
                "action": f"[{idx}/{total}] {reference} - {resource_name}",
                "percent": int((idx / total) * 100) if total > 0 else 0,
            }
            yield f"data: {json.dumps(progress_event)}\n\n"

            # Initialize result record
            result = {
                "row_num": row_num,
                "reference": reference,
                "resource_name": resource_name,
                "resource_id": resource_id,
                "invoice_id": None,
                "invoice_status": "pending",
                "payment_status": "pending",
                "payment_date_status": "pending",
                "document_status": "pending",
                "error": None,
            }

            # Skip rows with errors
            if row["status"] == "error":
                error_msg = ", ".join(row["errors"])
                yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] ERROR {reference} - {error_msg}'})}\n\n"
                errors += 1
                result["invoice_status"] = "error"
                result["payment_status"] = "skipped"
                result["payment_date_status"] = "skipped"
                result["document_status"] = "skipped"
                result["error"] = error_msg
                results.append(result)
                continue

            # Step 1: Create provider invoice
            yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] POST /provider-invoices ({reference})'})}\n\n"

            success, invoice_id, error = await client.create_provider_invoice(
                resource_id=resource_id,
                reference=reference,
                invoice_date=row["invoice_date"],
                start_date=row["start_date"],
                end_date=row["end_date"],
                amount_excluding_tax=row["amount_excluding_tax"],
                amount_including_tax=row["amount_including_tax"],
            )

            if not success:
                yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] ERROR {reference} - Creation echouee: {error}'})}\n\n"
                errors += 1
                result["invoice_status"] = "error"
                result["payment_status"] = "skipped"
                result["payment_date_status"] = "skipped"
                result["document_status"] = "skipped"
                result["error"] = error
                results.append(result)
                await asyncio.sleep(api_delay_ms / 1000.0)
                continue

            yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] OK {reference} - {resource_name} - Cree (ID: {invoice_id})'})}\n\n"
            invoices_created += 1
            result["invoice_id"] = invoice_id
            result["invoice_status"] = "created"

            # Step 2: Add payment if purchase_id found
            payment_id = None
            if row["purchase_id"]:
                yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] PUT /provider-invoices/{invoice_id} (payment)'})}\n\n"

                pay_success, payment_id, pay_error = await client.update_provider_invoice_payment(
                    invoice_id=invoice_id,
                    resource_id=resource_id,
                    purchase_id=row["purchase_id"],
                    amount_excluding_tax=row["amount_excluding_tax"],
                    amount_including_tax=row["amount_including_tax"],
                    payment_state=row["payment_state"],
                )

                if pay_success:
                    purchase_id_val = row["purchase_id"]
                    yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] OK {reference} - Payment ajoute (purchase: {purchase_id_val})'})}\n\n"
                    payments_added += 1
                    result["payment_status"] = "added"
                else:
                    yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] WARN {reference} - Payment echoue: {pay_error}'})}\n\n"
                    result["payment_status"] = "error"
                    result["error"] = pay_error
            else:
                yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] WARN {reference} - Purchase non trouve, pas de payment'})}\n\n"
                without_purchase += 1
                result["payment_status"] = "no_purchase"

            # Step 3: Update payment date (use paid_date or default to Dec 31st of prestation year)
            if payment_id:
                # Use provided date or default to last day of prestation year
                if row["paid_date"]:
                    paid_date_val = row["paid_date"]
                else:
                    # Default to December 31st of prestation year (extracted from start_date)
                    start_date = row.get("start_date", "")
                    if start_date and len(start_date) >= 4:
                        prestation_year = start_date[:4]  # Extract YYYY from YYYY-MM-DD
                        paid_date_val = f"{prestation_year}-12-31"
                    else:
                        paid_date_val = None

                if paid_date_val:
                    yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] PUT /payments/{payment_id} (performedDate: {paid_date_val})'})}\n\n"

                    date_success, date_error = await client.update_payment_date(
                        payment_id=payment_id,
                        performed_date=paid_date_val,
                    )

                    if date_success:
                        yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] OK {reference} - Date paiement mise a jour: {paid_date_val}'})}\n\n"
                        result["payment_date_status"] = "updated"
                    else:
                        yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] WARN {reference} - Mise a jour date echouee: {date_error}'})}\n\n"
                        result["payment_date_status"] = "error"
                else:
                    yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] WARN {reference} - Pas d annee, date non mise a jour'})}\n\n"
                    result["payment_date_status"] = "skipped"
            else:
                result["payment_date_status"] = "na"

            # Step 4: Attach document if file exists
            if row["file_status"] == "found":
                file_path = PROVIDER_INVOICES_FOLDER / row["invoice_file"]
                invoice_file_name = row["invoice_file"]
                yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] POST /documents ({invoice_file_name})'})}\n\n"

                doc_success, doc_error = await client.upload_document_to_provider_invoice(
                    invoice_id=invoice_id,
                    file_path=file_path,
                )

                if doc_success:
                    yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] OK {reference} - Document attache'})}\n\n"
                    documents_attached += 1
                    result["document_status"] = "attached"
                else:
                    yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] WARN {reference} - Document echoue: {doc_error}'})}\n\n"
                    result["document_status"] = "error"
            elif row["file_status"] == "na":
                result["document_status"] = "na"
            else:
                missing_file_name = row["invoice_file"]
                yield f"data: {json.dumps({'type': 'action', 'message': f'[{idx}/{total}] WARN {reference} - Fichier non trouve: {missing_file_name}'})}\n\n"
                without_document += 1
                result["document_status"] = "file_missing"

            results.append(result)

            # Delay between API calls
            if api_delay_ms > 0:
                await asyncio.sleep(api_delay_ms / 1000.0)

        # Send final result with CSV data
        final_result = {
            "type": "complete",
            "stats": {
                "total": total,
                "invoices_created": invoices_created,
                "payments_added": payments_added,
                "documents_attached": documents_attached,
                "without_purchase": without_purchase,
                "without_document": without_document,
                "errors": errors,
            },
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
