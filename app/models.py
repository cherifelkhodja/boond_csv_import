"""Pydantic models for CSV import validation and API responses."""

from typing import Any
from pydantic import BaseModel, Field


# Field definitions for each entity type
# Maps CSV field names to (api_attribute_name, is_required, is_relationship, relationship_type)
PROJECT_FIELDS: dict[str, tuple[str, bool, bool, str | None]] = {
    "company_id": ("company", True, True, "company"),
    "type_of": ("typeOf", True, False, None),
    "reference": ("reference", False, False, None),
    "state": ("state", False, False, None),
    "mode": ("mode", False, False, None),
    "start_date": ("startDate", False, False, None),
    "end_date": ("endDate", False, False, None),
    "currency": ("currency", False, False, None),
    "exchange_rate": ("exchangeRate", False, False, None),
    "work_unit_rate": ("workUnitRate", False, False, None),
    "additional_turnover": ("additionalTurnover", False, False, None),
    "additional_investment": ("additionalInvestment", False, False, None),
    "remains_to_be_done": ("remainsToBeDone", False, False, None),
    "comments": ("comments", False, False, None),
    "delivery_address": ("deliveryAddress", False, False, None),
    "delivery_postcode": ("deliveryPostcode", False, False, None),
    "delivery_town": ("deliveryTown", False, False, None),
    "delivery_country": ("deliveryCountry", False, False, None),
    "delivery_subdivision": ("deliverySubdivision", False, False, None),
    "contact_id": ("contact", False, True, "contact"),
    "technical_contact_id": ("technicalContact", False, True, "contact"),
    "main_manager_id": ("mainManager", False, True, "resource"),
    "resource_id": ("resource", False, True, "resource"),  # Ressource/candidat pour le positionnement
    "agency_id": ("agency", False, True, "agency"),
    "pole_id": ("pole", False, True, "pole"),
    "opportunity_id": ("opportunity", False, True, "opportunity"),
    "billing_intermediary_company_id": ("billingIntermediaryCompany", False, True, "company"),
    "billing_intermediary_contact_id": ("billingIntermediaryContact", False, True, "contact"),
}

DELIVERY_FIELDS: dict[str, tuple[str, bool, bool, str | None]] = {
    "project_id": ("project", True, True, "project"),
    "resource_id": ("dependsOn", True, True, "resource"),  # API uses "dependsOn" for resource
    "title": ("title", False, False, None),
    "start_date": ("startDate", False, False, None),
    "end_date": ("endDate", False, False, None),
    "state": ("state", False, False, None),
    "type_of": ("typeOf", False, False, None),
    "average_daily_price_excluding_tax": ("averageDailyPriceExcludingTax", False, False, None),
    "force_average_daily_price": ("forceAverageDailyPriceExcludingTax", False, False, None),
    "number_of_days_invoiced": ("numberOfDaysInvoicedOrQuantity", False, False, None),
    "number_of_days_free": ("numberOfDaysFree", False, False, None),
    "work_unit_rate": ("workUnitRate", False, False, None),
    "comments": ("informationComments", False, False, None),
    "contact_id": ("contact", False, True, "contact"),
    "positioning_id": ("positioning", False, True, "positioning"),
    # Order fields - used for auto-creating order after delivery
    "order_number": ("_order_number", False, False, None),
    "order_informationComments": ("_order_comments", False, False, None),
    "order_billingDetail": ("_order_billingDetail", False, False, None),
    "order_bankDetail": ("_order_bankDetail", False, False, None),
}

ORDER_FIELDS: dict[str, tuple[str, bool, bool, str | None]] = {
    "project_id": ("project", True, True, "project"),
    "reference": ("reference", True, False, None),
    "turnover_excluding_tax": ("turnoverExcludingTax", True, False, None),
    "customer_reference": ("customerReference", False, False, None),
    "date": ("date", False, False, None),
    "state": ("state", False, False, None),
    "billing_type": ("billingType", False, False, None),
    "turnover_including_tax": ("turnoverIncludingTax", False, False, None),
    "tax_rate": ("taxRate", False, False, None),
    "tax_rates": ("taxRates", False, False, None),
    "payment_terms": ("paymentTerms", False, False, None),
    "payment_method": ("paymentMethod", False, False, None),
    "language": ("language", False, False, None),
    "comments": ("comments", False, False, None),
    "billing_instructions": ("billingInstructions", False, False, None),
    "invoice_legals": ("invoiceLegals", False, False, None),
    "customer_agreement": ("customerAgreement", False, False, None),
    "show_order_number": ("showOrderNumber", False, False, None),
    "show_project_reference": ("showProjectReference", False, False, None),
    "show_resource_name": ("showResourceName", False, False, None),
    "show_working_days": ("showWorkingDays", False, False, None),
    "show_daily_prices": ("showDailyPrices", False, False, None),
    "show_bank_details": ("showBankDetails", False, False, None),
    "show_vat_number": ("showVatNumber", False, False, None),
    "show_factor": ("showFactor", False, False, None),
    "show_footer": ("showFooter", False, False, None),
    "show_comments": ("showComments", False, False, None),
    "separate_times_expenses": ("separateTimesExpenses", False, False, None),
    "separate_exceptional_activities": ("separateExceptionalActivities", False, False, None),
    "group_mission": ("groupMission", False, False, None),
    "group_expenses": ("groupExpenses", False, False, None),
    "copy_comments": ("copyComments", False, False, None),
    "attach_signed_timesheets": ("attachSignedTimesheets", False, False, None),
    "attach_unsigned_timesheets": ("attachUnsignedTimesheets", False, False, None),
    "attach_expenses": ("attachExpenses", False, False, None),
    "request_timesheets_signature": ("requestTimesheetsSignature", False, False, None),
    "merge_invoice_attachments": ("mergeInvoiceAttachments", False, False, None),
    "main_manager_id": ("mainManager", False, True, "resource"),
    "billing_details_id": ("billingDetails", False, True, "billingDetails"),
    "head_office_id": ("headOffice", False, True, "headOffice"),
    "bank_details_id": ("bankDetails", False, True, "bankDetails"),
    "factor_id": ("factor", False, True, "factor"),
    "delivery_ids": ("deliveries", False, False, None),  # Special handling for POST relationship
}

PURCHASE_FIELDS: dict[str, tuple[str, bool, bool, str | None]] = {
    "project_id": ("project", True, True, "project"),
    "title": ("title", True, False, None),
    "amount_excluding_tax": ("amountExcludingTax", True, False, None),
    "reference": ("reference", False, False, None),
    "date": ("date", False, False, None),
    "state": ("state", False, False, None),
    "tax_rate": ("taxRate", False, False, None),
    "tax_rates": ("taxRates", False, False, None),
    "amount_including_tax": ("amountIncludingTax", False, False, None),
    "payment_terms": ("paymentTerms", False, False, None),
    "payment_method": ("paymentMethod", False, False, None),
    "rebillable": ("rebillable", False, False, None),
    "rebillable_rate": ("rebillableRate", False, False, None),
    "comments": ("comments", False, False, None),
    "delivery_id": ("delivery", False, True, "delivery"),
    "resource_id": ("resource", False, True, "resource"),
    "vendor_id": ("vendor", False, True, "company"),
    "vendor_contact_id": ("vendorContact", False, True, "contact"),
    "main_manager_id": ("mainManager", False, True, "resource"),
}

# Contract fields - dependsOn is handled specially (resource OR candidate)
CONTRACT_FIELDS: dict[str, tuple[str, bool, bool, str | None]] = {
    # Required relationship - either resource_id or candidate_id must be provided
    "resource_id": ("dependsOn", False, True, "resource"),  # Handled specially
    "candidate_id": ("dependsOn", False, True, "candidate"),  # Handled specially
    # Optional relationships
    "agency_id": ("agency", False, True, "agency"),
    "parent_contract_id": ("parentContract", False, True, "contract"),
    # General information
    "type_of": ("typeOf", False, False, None),
    "employee_type": ("employeeType", False, False, None),
    "working_time_type": ("workingTimeType", False, False, None),
    "classification": ("classification", False, False, None),
    "comments": ("informationComments", False, False, None),
    # Dates
    "start_date": ("startDate", False, False, None),
    "end_date": ("endDate", False, False, None),
    "probation_end_date": ("probationEndDate", False, False, None),
    "renewal_probation_end_date": ("renewalProbationEndDate", False, False, None),
    "probation_state": ("probationState", False, False, None),
    # Working time
    "hours_per_week": ("numberOfHoursPerWeek", False, False, None),
    "working_days": ("numberOfWorkingDays", False, False, None),
    "activity_rate": ("activityRate", False, False, None),
    "calendar": ("calendar", False, False, None),
    # Salary
    "monthly_salary": ("monthlySalary", False, False, None),
    "hourly_salary": ("hourlySalary", False, False, None),
    "force_hourly_salary": ("forceHourlySalary", False, False, None),
    "charge_factor": ("chargeFactor", False, False, None),
    # Costs (external resources)
    "force_daily_cost": ("forceContractAverageDailyProductionCost", False, False, None),
    "daily_production_cost": ("contractAverageDailyProductionCost", False, False, None),
    "daily_expenses": ("dailyExpenses", False, False, None),
    "monthly_expenses": ("monthlyExpenses", False, False, None),
    # Currency
    "currency": ("currency", False, False, None),
    "exchange_rate": ("exchangeRate", False, False, None),
}

# Entity type configurations
ENTITY_CONFIGS = {
    "projects": {
        "fields": PROJECT_FIELDS,
        "api_type": "project",
        "endpoint": "/projects",
        "template_fields": [
            "company_id", "type_of", "reference", "contact_id",
            "main_manager_id", "resource_id", "agency_id", "opportunity_id",
        ],
    },
    "deliveries": {
        "fields": DELIVERY_FIELDS,
        "api_type": "delivery",
        "endpoint": "/deliveries",
        "template_fields": [
            "project_id", "resource_id", "title", "start_date", "end_date",
            "average_daily_price_excluding_tax", "number_of_days_invoiced", "number_of_days_free",
            "order_number", "order_informationComments", "order_billingDetail", "order_bankDetail",
        ],
    },
    "orders": {
        "fields": ORDER_FIELDS,
        "api_type": "order",
        "endpoint": "/orders",
        "template_fields": [
            "project_id", "reference", "turnover_excluding_tax", "date",
        ],
    },
    "purchases": {
        "fields": PURCHASE_FIELDS,
        "api_type": "purchase",
        "endpoint": "/purchases",
        "template_fields": [
            "project_id", "title", "amount_excluding_tax", "date",
        ],
    },
    "contracts": {
        "fields": CONTRACT_FIELDS,
        "api_type": "contract",
        "endpoint": "/contracts",
        "template_fields": [
            "resource_id", "candidate_id", "agency_id", "type_of", "employee_type",
            "working_time_type", "classification", "start_date", "end_date",
            "probation_state", "probation_end_date", "renewal_probation_end_date",
            "hours_per_week", "working_days", "activity_rate", "calendar",
            "monthly_salary", "hourly_salary", "force_hourly_salary", "charge_factor",
            "force_daily_cost", "daily_production_cost", "daily_expenses", "monthly_expenses",
            "currency", "exchange_rate", "parent_contract_id", "comments",
        ],
    },
}


# Response models
class ValidationError(BaseModel):
    """Single validation error."""

    row: int
    field: str
    error: str


class ValidationResponse(BaseModel):
    """Response for CSV validation."""

    valid: bool
    total_rows: int
    errors: list[ValidationError] = Field(default_factory=list)


class ImportResult(BaseModel):
    """Single import result."""

    row: int
    status: str  # "success" or "error"
    id: str | None = None
    message: str | None = None
    original_data: dict[str, Any] = Field(default_factory=dict)


class ImportResponse(BaseModel):
    """Response for CSV import."""

    total: int
    success: int
    failed: int
    results: list[ImportResult] = Field(default_factory=list)


class ConnectionTestResponse(BaseModel):
    """Response for connection test."""

    success: bool
    message: str
