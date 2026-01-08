"""Router for analyzing discrepancies between provider invoices and activity expenses."""

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Body, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.boond_client import get_boond_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ecarts", tags=["Ecarts Analysis"])

DEFAULT_API_DELAY_MS = 100


class AnalyzeRequest(BaseModel):
    """Request model for analyze endpoint."""
    agency_id: Optional[str] = None
    start_date: str
    end_date: str


class UpdateStatesRequest(BaseModel):
    """Request model for update states endpoint."""
    invoices: list[dict]
    new_state: int = 5


@router.get("/agencies")
async def get_agencies():
    """Get list of agencies for dropdown."""
    client = get_boond_client()
    success, agencies, error = await client.get_agencies()

    if not success:
        return {"success": False, "error": error}

    return {"success": True, "agencies": agencies}


@router.post("/analyze")
async def analyze_ecarts(request: AnalyzeRequest) -> StreamingResponse:
    """
    Analyze discrepancies between provider invoices and activity expenses.
    Returns Server-Sent Events for real-time progress.
    """
    async def generate_events():
        client = get_boond_client()

        # Step 1: Get provider invoices
        yield f"data: {json.dumps({'type': 'status', 'message': 'Recuperation des factures fournisseurs...'})}\n\n"

        success, invoices, error = await client.get_provider_invoices_with_filters(
            agency_id=request.agency_id,
            invoice_date_from=request.start_date,
            invoice_date_to=request.end_date,
        )

        if not success:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Erreur: {error}'})}\n\n"
            return

        if not invoices:
            yield f"data: {json.dumps({'type': 'complete', 'message': 'Aucune facture trouvee', 'data': {'factures': [], 'stats': {}}})}\n\n"
            return

        total = len(invoices)
        yield f"data: {json.dumps({'type': 'status', 'message': f'{total} factures trouvees. Analyse des activites...'})}\n\n"

        # Step 2: Get activity expenses for each invoice
        results = []
        ecart_total = 0
        ecart_positif_count = 0
        ecart_negatif_count = 0
        sans_ecart_count = 0
        sans_activite_count = 0

        for idx, invoice in enumerate(invoices, start=1):
            invoice_id = invoice["id"]
            reference = invoice["reference"]
            start_date = invoice["startDate"]
            end_date = invoice["endDate"]
            amount_facture = float(invoice["amountExcludingTax"] or 0)

            # Progress
            progress_event = {
                "type": "progress",
                "current": idx,
                "total": total,
                "percent": int((idx / total) * 100),
                "message": f"[{idx}/{total}] {reference}",
            }
            yield f"data: {json.dumps(progress_event)}\n\n"

            # Get activity expenses
            if start_date and end_date:
                success, activity_amount, _ = await client.get_activity_expenses(
                    invoice_id=invoice_id,
                    start_date=start_date,
                    end_date=end_date,
                )
                if not success:
                    activity_amount = 0
            else:
                activity_amount = 0

            # Calculate ecart
            ecart = amount_facture - activity_amount
            if activity_amount > 0:
                ecart_percent = round((ecart / activity_amount) * 100, 2)
            else:
                ecart_percent = None

            # Update counters
            ecart_total += ecart
            if activity_amount == 0:
                sans_activite_count += 1
            elif ecart > 0:
                ecart_positif_count += 1
            elif ecart < 0:
                ecart_negatif_count += 1
            else:
                sans_ecart_count += 1

            results.append({
                "id": invoice_id,
                "reference": reference,
                "resource_id": invoice["resource_id"],
                "resource_name": invoice["resource_name"],
                "invoiceDate": invoice["invoiceDate"],
                "startDate": start_date,
                "endDate": end_date,
                "amountExcludingTax": amount_facture,
                "activityAmount": activity_amount,
                "ecart": ecart,
                "ecart_percent": ecart_percent,
                "state": invoice["state"],
            })

            # Small delay to avoid overwhelming the API
            await asyncio.sleep(DEFAULT_API_DELAY_MS / 1000.0)

        # Calculate stats
        ecart_moyen = ecart_total / total if total > 0 else 0

        stats = {
            "total": total,
            "ecart_total": round(ecart_total, 2),
            "ecart_moyen": round(ecart_moyen, 2),
            "ecart_positif": ecart_positif_count,
            "ecart_negatif": ecart_negatif_count,
            "sans_ecart": sans_ecart_count,
            "sans_activite": sans_activite_count,
        }

        # Send final result
        final_result = {
            "type": "complete",
            "data": {
                "factures": results,
                "stats": stats,
            }
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


@router.post("/update-states")
async def update_states(request: UpdateStatesRequest) -> StreamingResponse:
    """
    Update state of all analyzed invoices to a new state.
    Returns Server-Sent Events for real-time progress.
    """
    async def generate_events():
        client = get_boond_client()
        invoices = request.invoices
        new_state = request.new_state
        total = len(invoices)

        if total == 0:
            yield f"data: {json.dumps({'type': 'complete', 'stats': {'total': 0, 'success': 0, 'errors': 0}, 'errors': []})}\n\n"
            return

        success_count = 0
        error_count = 0
        errors_list = []

        for idx, invoice in enumerate(invoices, start=1):
            invoice_id = invoice["id"]
            resource_id = invoice["resource_id"]
            reference = invoice.get("reference", invoice_id)

            # Progress
            progress_event = {
                "type": "progress",
                "current": idx,
                "total": total,
                "percent": int((idx / total) * 100),
                "message": f"[{idx}/{total}] {reference}",
            }
            yield f"data: {json.dumps(progress_event)}\n\n"

            # Update state
            success, error = await client.update_provider_invoice_state(
                invoice_id=invoice_id,
                resource_id=resource_id,
                new_state=new_state,
            )

            if success:
                success_count += 1
                yield f"data: {json.dumps({'type': 'action', 'status': 'success', 'message': f'[{idx}/{total}] ✅ {reference} - State mis a jour → {new_state}'})}\n\n"
            else:
                error_count += 1
                errors_list.append({"id": invoice_id, "reference": reference, "error": error})
                yield f"data: {json.dumps({'type': 'action', 'status': 'error', 'message': f'[{idx}/{total}] ❌ {reference} - Erreur: {error}'})}\n\n"

            # Small delay
            await asyncio.sleep(DEFAULT_API_DELAY_MS / 1000.0)

        # Send final result
        final_result = {
            "type": "complete",
            "stats": {
                "total": total,
                "success": success_count,
                "errors": error_count,
            },
            "errors": errors_list,
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
