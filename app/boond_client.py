"""BoondManager API client for REST operations."""

import logging
import os
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.models import ENTITY_CONFIGS

logger = logging.getLogger(__name__)

# Documents folder path (relative to project root)
DOCUMENTS_FOLDER = Path(__file__).parent.parent / "documents"


class BoondClient:
    """Client for BoondManager API operations."""

    def __init__(self) -> None:
        """Initialize the client with settings."""
        settings = get_settings()
        self.base_url = settings.boond_base_url.rstrip("/")
        self.auth = (settings.boond_username, settings.boond_password)
        self.timeout = 30.0

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def test_connection(self) -> tuple[bool, str]:
        """Test the connection to BoondManager API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/application",
                    auth=self.auth,
                    headers=self._get_headers(),
                )
                if response.status_code == 200:
                    return True, "Connection successful"
                elif response.status_code == 401:
                    return False, "Authentication failed: Invalid credentials"
                else:
                    return False, f"Connection failed with status {response.status_code}"
            except httpx.ConnectError:
                return False, "Connection failed: Unable to reach BoondManager API"
            except httpx.TimeoutException:
                return False, "Connection failed: Request timeout"
            except Exception as e:
                return False, f"Connection failed: {str(e)}"

    def _build_payload(
        self,
        entity_type: str,
        row_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the JSON:API payload for entity creation."""
        config = ENTITY_CONFIGS[entity_type]
        fields = config["fields"]
        api_type = config["api_type"]

        attributes: dict[str, Any] = {}
        relationships: dict[str, Any] = {}

        for csv_field, value in row_data.items():
            if csv_field not in fields or value is None or value == "":
                continue

            api_name, _, is_relationship, rel_type = fields[csv_field]

            # Skip delivery_ids - handled separately for orders
            if csv_field == "delivery_ids":
                continue

            # Skip resource_id and candidate_id for contracts - handled specially
            if entity_type == "contracts" and csv_field in ("resource_id", "candidate_id"):
                continue

            if is_relationship:
                relationships[api_name] = {
                    "data": {
                        "id": str(value),
                        "type": rel_type,
                    }
                }
            else:
                attributes[api_name] = value

        payload: dict[str, Any] = {
            "data": {
                "type": api_type,
                "attributes": attributes,
            }
        }

        if relationships:
            payload["data"]["relationships"] = relationships

        # For deliveries: auto-set forceAverageDailyPriceExcludingTax when TJM is provided
        if entity_type == "deliveries" and "averageDailyPriceExcludingTax" in attributes:
            attributes["forceAverageDailyPriceExcludingTax"] = True

        # For contracts: build dependsOn relationship from resource_id or candidate_id
        if entity_type == "contracts":
            resource_id = row_data.get("resource_id")
            candidate_id = row_data.get("candidate_id")

            if resource_id:
                if "relationships" not in payload["data"]:
                    payload["data"]["relationships"] = {}
                payload["data"]["relationships"]["dependsOn"] = {
                    "data": {"type": "resource", "id": str(resource_id)}
                }
            elif candidate_id:
                if "relationships" not in payload["data"]:
                    payload["data"]["relationships"] = {}
                payload["data"]["relationships"]["dependsOn"] = {
                    "data": {"type": "candidate", "id": str(candidate_id)}
                }

        return payload

    async def _create_opportunity(
        self,
        title: str,
        contact_id: int | str,
        company_id: int | str,
        main_manager_id: int | str | None = None,
        agency_id: int | str | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """
        Create an opportunity (action) in BoondManager.

        Returns: (success, opportunity_id, error_message)
        """
        payload: dict[str, Any] = {
            "data": {
                "type": "opportunity",
                "attributes": {
                    "title": title,
                    "state": 1,  # État actif
                    "typeOf": 1,  # Type standard
                    "mode": 1,   # Mode standard
                },
                "relationships": {
                    "contact": {
                        "data": {
                            "id": str(contact_id),
                            "type": "contact",
                        }
                    },
                    "company": {
                        "data": {
                            "id": str(company_id),
                            "type": "company",
                        }
                    },
                },
            }
        }

        # Add main manager if provided
        if main_manager_id:
            payload["data"]["relationships"]["mainManager"] = {
                "data": {
                    "id": str(main_manager_id),
                    "type": "resource",
                }
            }

        # Add agency if provided
        if agency_id:
            payload["data"]["relationships"]["agency"] = {
                "data": {
                    "id": str(agency_id),
                    "type": "agency",
                }
            }

        logger.info(f"Creating opportunity with payload: {payload}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/opportunities",
                    json=payload,
                    auth=self.auth,
                    headers=self._get_headers(),
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    opportunity_id = data.get("data", {}).get("id")
                    logger.info(f"Created opportunity with ID: {opportunity_id}")
                    return True, opportunity_id, None
                else:
                    error_data = response.json() if response.content else {}
                    logger.warning(f"Opportunity API response: {error_data}")
                    error_msg = self._extract_error_message(error_data, response.status_code)
                    return False, None, error_msg

            except Exception as e:
                return False, None, str(e)

    async def _create_won_positioning(
        self,
        opportunity_id: int | str,
        resource_id: int | str,
        main_manager_id: int | str | None = None,
        agency_id: int | str | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """
        Create a won positioning for an opportunity.
        This is required to create projects in modes other than fixed/product.

        Returns: (success, positioning_id, error_message)
        """
        # State 2 = won (gagné) in BoondManager
        payload: dict[str, Any] = {
            "data": {
                "type": "positioning",
                "attributes": {
                    "state": 2,  # Won/Gagné
                },
                "relationships": {
                    "opportunity": {
                        "data": {
                            "id": str(opportunity_id),
                            "type": "opportunity",
                        }
                    },
                    "dependsOn": {
                        "data": {
                            "id": str(resource_id),
                            "type": "resource",
                        }
                    },
                },
            }
        }

        # Add main manager if provided
        if main_manager_id:
            payload["data"]["relationships"]["mainManager"] = {
                "data": {
                    "id": str(main_manager_id),
                    "type": "resource",
                }
            }

        # Add agency if provided
        if agency_id:
            payload["data"]["relationships"]["agency"] = {
                "data": {
                    "id": str(agency_id),
                    "type": "agency",
                }
            }

        logger.info(f"Creating won positioning with payload: {payload}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/positionings",
                    json=payload,
                    auth=self.auth,
                    headers=self._get_headers(),
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    positioning_id = data.get("data", {}).get("id")
                    # Get the automatically created project ID
                    project_data = data.get("data", {}).get("relationships", {}).get("project", {}).get("data")
                    project_id = project_data.get("id") if project_data else None
                    logger.info(f"Created won positioning with ID: {positioning_id}, project ID: {project_id}")
                    return True, project_id, None  # Return project_id instead of positioning_id
                else:
                    error_data = response.json() if response.content else {}
                    logger.warning(f"Positioning API response: {error_data}")
                    error_msg = self._extract_error_message(error_data, response.status_code)
                    return False, None, error_msg

            except Exception as e:
                return False, None, str(e)

    async def create_entity(
        self,
        entity_type: str,
        row_data: dict[str, Any],
    ) -> tuple[bool, str | None, str | None]:
        """
        Create an entity in BoondManager.

        Returns: (success, entity_id, error_message)
        """
        # For projects, handle opportunity and positioning creation
        if entity_type == "projects":
            opportunity_id = row_data.get("opportunity_id")
            mode = row_data.get("mode")
            resource_id = row_data.get("resource_id")  # Candidat/ressource pour le positionnement
            main_manager_id = row_data.get("main_manager_id")  # Manager de l'opportunity
            contact_id = row_data.get("contact_id")
            company_id = row_data.get("company_id")
            title = row_data.get("reference") or "Nouveau projet"

            # If mode is not fixed(1) or product(2), we need positioning
            if mode not in (1, 2, "1", "2"):
                if not resource_id:
                    return False, None, "resource_id requis pour créer un positionnement"

                # If no opportunity provided, create one first
                if not opportunity_id:
                    if not contact_id:
                        return False, None, "contact_id requis pour créer une opportunité"
                    if not company_id:
                        return False, None, "company_id requis pour créer une opportunité"

                    agency_id = row_data.get("agency_id")
                    logger.info(f"Creating opportunity '{title}' for contact {contact_id}")
                    success, new_opp_id, error = await self._create_opportunity(
                        title, contact_id, company_id, main_manager_id, agency_id
                    )
                    if not success:
                        return False, None, f"Erreur création opportunité: {error}"

                    opportunity_id = new_opp_id
                    row_data["opportunity_id"] = opportunity_id
                    logger.info(f"Opportunity created with ID: {opportunity_id}")

                # Create won positioning - this automatically creates the project
                agency_id = row_data.get("agency_id")
                logger.info(f"Creating won positioning for opportunity {opportunity_id}")
                success, project_id, error = await self._create_won_positioning(
                    opportunity_id, resource_id, main_manager_id, agency_id
                )
                if not success:
                    return False, None, f"Erreur création positionnement: {error}"

                # The project is created automatically, return its ID
                if project_id:
                    logger.info(f"Project created automatically with ID: {project_id}")
                    return True, project_id, None
                else:
                    return False, None, "Positionnement créé mais ID projet non trouvé"

        config = ENTITY_CONFIGS[entity_type]
        endpoint = config["endpoint"]
        payload = self._build_payload(entity_type, row_data)

        logger.info(f"Creating {entity_type} with payload: {payload}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}{endpoint}",
                    json=payload,
                    auth=self.auth,
                    headers=self._get_headers(),
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    entity_id = data.get("data", {}).get("id")
                    logger.info(f"Created {entity_type} with ID: {entity_id}")

                    # Handle order-delivery relationship if delivery_ids provided
                    if entity_type == "orders" and "delivery_ids" in row_data:
                        delivery_ids = row_data["delivery_ids"]
                        if delivery_ids:
                            await self._link_order_deliveries(entity_id, delivery_ids)

                    # For deliveries: auto-create purchase (if external) and order
                    if entity_type == "deliveries":
                        resource_id = row_data.get("resource_id")
                        project_id = row_data.get("project_id")
                        order_number = row_data.get("order_number")
                        purchase_id = None

                        if resource_id and project_id:
                            success, resource_data, _ = await self._get_resource_info(resource_id)
                            if success and resource_data:
                                type_of = resource_data.get("attributes", {}).get("typeOf")
                                if type_of in (1, 10):
                                    # External consultant - create purchase
                                    first_name = resource_data.get("attributes", {}).get("firstName", "")
                                    last_name = resource_data.get("attributes", {}).get("lastName", "")
                                    resource_name = f"{last_name.upper()} {first_name}"
                                    start_date = row_data.get("start_date", "")

                                    purchase_success, purchase_id, purchase_error = await self._create_purchase_for_delivery(
                                        entity_id, project_id, resource_name, start_date
                                    )
                                    if purchase_success:
                                        logger.info(f"Auto-created purchase {purchase_id} for external consultant")
                                    else:
                                        logger.warning(f"Failed to auto-create purchase: {purchase_error}")
                                        purchase_id = None

                        # Create order if order_number is provided
                        if order_number and project_id:
                            order_success, order_id, order_error = await self._create_order_for_delivery(
                                entity_id, project_id, purchase_id, row_data
                            )
                            if order_success:
                                logger.info(f"Auto-created order {order_id} for delivery {entity_id}")

                                # Try to upload documents to the order
                                contrat = row_data.get("contrat", "") or row_data.get("Contrat", "")
                                doc_paths = self._find_documents_for_order(order_number, contrat)
                                for doc_path in doc_paths:
                                    doc_success, doc_error = await self._upload_document_to_order(
                                        order_id, doc_path
                                    )
                                    if doc_success:
                                        logger.info(f"Uploaded document {doc_path.name} to order {order_id}")
                                    else:
                                        logger.warning(f"Failed to upload document {doc_path.name}: {doc_error}")
                            else:
                                logger.warning(f"Failed to auto-create order: {order_error}")

                    return True, entity_id, None
                else:
                    error_data = response.json() if response.content else {}
                    logger.warning(f"API response status: {response.status_code}")
                    logger.warning(f"API response body: {error_data}")
                    error_msg = self._extract_error_message(error_data, response.status_code)
                    logger.warning(f"Failed to create {entity_type}: {error_msg}")
                    return False, None, error_msg

            except httpx.ConnectError:
                error_msg = "Unable to connect to BoondManager API"
                logger.error(error_msg)
                return False, None, error_msg
            except httpx.TimeoutException:
                error_msg = "Request timeout"
                logger.error(error_msg)
                return False, None, error_msg
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Unexpected error: {error_msg}")
                return False, None, error_msg

    async def _link_order_deliveries(self, order_id: str, delivery_ids: str) -> None:
        """Link deliveries to an order."""
        # Parse delivery_ids (comma-separated)
        ids = [d.strip() for d in delivery_ids.split(",") if d.strip()]
        if not ids:
            return

        payload = {
            "data": [{"id": d_id, "type": "delivery"} for d_id in ids]
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/orders/{order_id}/relationships/deliveries",
                    json=payload,
                    auth=self.auth,
                    headers=self._get_headers(),
                )
                if response.status_code in (200, 201, 204):
                    logger.info(f"Linked deliveries {ids} to order {order_id}")
                else:
                    logger.warning(
                        f"Failed to link deliveries to order {order_id}: "
                        f"status {response.status_code}"
                    )
            except Exception as e:
                logger.warning(f"Failed to link deliveries to order {order_id}: {e}")

    async def _get_resource_info(
        self,
        resource_id: int | str,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        """
        Get resource information from BoondManager.

        Returns: (success, resource_data, error_message)
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/resources/{resource_id}",
                    auth=self.auth,
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    data = response.json()
                    return True, data.get("data", {}), None
                else:
                    return False, None, f"Erreur API: {response.status_code}"

            except Exception as e:
                return False, None, str(e)

    async def _create_purchase_for_delivery(
        self,
        delivery_id: str,
        project_id: str,
        resource_name: str,
        start_date: str,
    ) -> tuple[bool, str | None, str | None]:
        """
        Create a purchase linked to a delivery for external consultants.

        Returns: (success, purchase_id, error_message)
        """
        # Build purchase title: "LASTNAME FirstName - DEL{delivery_id}"
        title = f"{resource_name} - DEL{delivery_id}"

        payload: dict[str, Any] = {
            "data": {
                "type": "purchase",
                "attributes": {
                    "date": start_date,
                    "title": title,
                    "createPayments": "manually",
                },
                "relationships": {
                    "delivery": {
                        "data": {
                            "id": str(delivery_id),
                            "type": "delivery",
                        }
                    },
                    "project": {
                        "data": {
                            "id": str(project_id),
                            "type": "project",
                        }
                    },
                },
            }
        }

        logger.info(f"Creating purchase for delivery {delivery_id} with payload: {payload}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/purchases",
                    json=payload,
                    auth=self.auth,
                    headers=self._get_headers(),
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    purchase_id = data.get("data", {}).get("id")
                    logger.info(f"Created purchase {purchase_id} for delivery {delivery_id}")
                    return True, purchase_id, None
                else:
                    error_data = response.json() if response.content else {}
                    logger.warning(f"Purchase API response: {error_data}")
                    error_msg = self._extract_error_message(error_data, response.status_code)
                    return False, None, error_msg

            except Exception as e:
                return False, None, str(e)

    async def _create_order_for_delivery(
        self,
        delivery_id: str,
        project_id: str,
        purchase_id: str | None,
        row_data: dict[str, Any],
    ) -> tuple[bool, str | None, str | None]:
        """
        Create an order linked to a delivery (and purchase if external consultant).

        Returns: (success, order_id, error_message)
        """
        # Get order fields from row_data
        order_number = row_data.get("order_number", "")
        order_comments = row_data.get("order_informationComments", "")
        # Convert literal \n to actual newlines
        if order_comments:
            order_comments = order_comments.replace("\\n", "\n")
        billing_detail_id = row_data.get("order_billingDetail")
        bank_detail_id = row_data.get("order_bankDetail")
        start_date = row_data.get("start_date", "")
        tjm = row_data.get("average_daily_price_excluding_tax", 0)
        nb_days = row_data.get("number_of_days_invoiced", 0)

        # Calculate turnover
        turnover = float(tjm) * float(nb_days) if tjm and nb_days else 0

        # Build deliveriesPurchases based on whether purchase exists
        deliveries_purchases = [{"type": "delivery", "id": str(delivery_id)}]
        if purchase_id:
            deliveries_purchases.append({"type": "purchase", "id": str(purchase_id)})

        payload: dict[str, Any] = {
            "data": {
                "type": "order",
                "attributes": {
                    "number": order_number,
                    "date": start_date,
                    "state": 1,
                    "customerAgreement": True,
                    "turnoverOrderedExcludingTax": turnover,
                    "informationComments": order_comments,
                },
                "relationships": {
                    "project": {
                        "data": {"type": "project", "id": str(project_id)}
                    },
                    "deliveriesPurchases": {
                        "data": deliveries_purchases
                    },
                },
            }
        }

        # Add billingDetail if provided
        if billing_detail_id:
            payload["data"]["relationships"]["billingDetail"] = {
                "data": {"type": "detail", "id": str(billing_detail_id)}
            }

        # Add bankDetail if provided
        if bank_detail_id:
            payload["data"]["relationships"]["bankDetail"] = {
                "data": {"type": "bankdetail", "id": str(bank_detail_id)}
            }

        logger.info(f"Creating order for delivery {delivery_id} with payload: {payload}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/orders",
                    json=payload,
                    auth=self.auth,
                    headers=self._get_headers(),
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    order_id = data.get("data", {}).get("id")
                    logger.info(f"Created order {order_id} for delivery {delivery_id}")
                    return True, order_id, None
                else:
                    error_data = response.json() if response.content else {}
                    logger.warning(f"Order API response: {error_data}")
                    error_msg = self._extract_error_message(error_data, response.status_code)
                    return False, None, error_msg

            except Exception as e:
                return False, None, str(e)

    def _find_documents_for_order(
        self,
        order_number: str,
        contrat: str = "",
    ) -> list[Path]:
        """
        Find documents in ./documents/ folder matching order_number and/or contrat.

        Search criteria (case insensitive):
        - If order_number is provided (and not "PO"): search for order_number in filename
        - If contrat is provided: search for contrat in filename
        - If both are provided, search for BOTH and return all matching documents

        For each reference, if multiple files match, the most recently modified one is selected.

        Returns: List of paths to matching files (one per reference that matched).
        """
        logger.info(f"Searching documents in: {DOCUMENTS_FOLDER}")
        logger.info(f"order_number='{order_number}', contrat='{contrat}'")

        if not DOCUMENTS_FOLDER.exists():
            logger.warning(f"Documents folder not found: {DOCUMENTS_FOLDER}")
            return []

        # List all files in folder for debugging
        all_files = [f.name for f in DOCUMENTS_FOLDER.iterdir() if f.is_file()]
        logger.info(f"Files in documents folder: {all_files}")

        # Build list of references to search for
        search_refs: list[str] = []
        if order_number and order_number.upper() != "PO":
            search_refs.append(order_number)
        if contrat:
            search_refs.append(contrat)

        logger.info(f"Search references: {search_refs}")

        if not search_refs:
            logger.info("No order_number or contrat provided for document search")
            return []

        result_files: list[Path] = []
        seen_files: set[Path] = set()

        for search_ref in search_refs:
            matching_files: list[tuple[Path, float]] = []

            for file_path in DOCUMENTS_FOLDER.iterdir():
                if not file_path.is_file():
                    continue

                file_name = file_path.name

                # Check if filename contains the search reference (case insensitive)
                if search_ref.lower() in file_name.lower():
                    mtime = file_path.stat().st_mtime
                    matching_files.append((file_path, mtime))
                    logger.debug(f"Found matching file ({search_ref}): {file_name}")

            if matching_files:
                # Sort by modification time (most recent first) and select the first
                matching_files.sort(key=lambda x: x[1], reverse=True)
                selected_file = matching_files[0][0]

                # Avoid duplicates if same file matches both references
                if selected_file not in seen_files:
                    seen_files.add(selected_file)
                    result_files.append(selected_file)
                    logger.info(f"Selected document for '{search_ref}': {selected_file.name}")
            else:
                logger.info(f"No document found for reference={search_ref}")

        return result_files

    async def _upload_document_to_order(
        self,
        order_id: str,
        file_path: Path,
    ) -> tuple[bool, str | None]:
        """
        Upload a document to an order via POST /documents.

        Uses multipart/form-data with:
        - file: the document file
        - parentType: "order"
        - parentId: the order ID

        Returns: (success, error_message)
        """
        if not file_path.exists():
            return False, f"File not found: {file_path}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                with open(file_path, "rb") as f:
                    files = {"file": (file_path.name, f, "application/octet-stream")}
                    data = {
                        "parentType": "order",
                        "parentId": str(order_id),
                    }

                    response = await client.post(
                        f"{self.base_url}/documents",
                        files=files,
                        data=data,
                        auth=self.auth,
                        headers={"Accept": "application/json"},
                    )

                if response.status_code in (200, 201):
                    logger.info(f"Uploaded document {file_path.name} to order {order_id}")
                    return True, None
                else:
                    error_data = response.json() if response.content else {}
                    logger.warning(f"Document upload API response: {error_data}")
                    error_msg = self._extract_error_message(error_data, response.status_code)
                    return False, error_msg

            except Exception as e:
                logger.error(f"Failed to upload document: {e}")
                return False, str(e)

    async def update_resource_type(
        self,
        resource_id: str,
        type_of: int,
    ) -> tuple[bool, str | None]:
        """
        Update resource type via PUT /resources/{resource_id}/informations.

        Args:
            resource_id: The resource ID
            type_of: The type ID to set

        Returns: (success, error_message)
        """
        payload = {
            "data": {
                "type": "resource",
                "id": str(resource_id),
                "attributes": {
                    "typeOf": type_of,
                },
            }
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.put(
                    f"{self.base_url}/resources/{resource_id}/information",
                    json=payload,
                    auth=self.auth,
                    headers=self._get_headers(),
                )

                if response.status_code in (200, 201):
                    logger.info(f"Updated resource {resource_id} type to {type_of}")
                    return True, None
                else:
                    error_data = response.json() if response.content else {}
                    error_msg = self._extract_error_message(error_data, response.status_code)
                    logger.warning(f"Failed to update resource type: {error_msg}")
                    return False, error_msg

            except Exception as e:
                logger.error(f"Failed to update resource type: {e}")
                return False, str(e)

    async def get_company_first_contact(
        self,
        company_id: str,
    ) -> tuple[bool, str | None, str | None]:
        """
        Get the first contact of a company via GET /companies/{company_id}/contacts.

        Args:
            company_id: The company ID

        Returns: (success, contact_id, error_message)
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/companies/{company_id}/contacts",
                    auth=self.auth,
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    data = response.json()
                    contacts = data.get("data", [])
                    if contacts and len(contacts) > 0:
                        contact_id = contacts[0].get("id")
                        logger.info(f"Found contact {contact_id} for company {company_id}")
                        return True, contact_id, None
                    else:
                        logger.warning(f"No contacts found for company {company_id}")
                        return True, None, "No contacts found"
                else:
                    error_data = response.json() if response.content else {}
                    error_msg = self._extract_error_message(error_data, response.status_code)
                    logger.warning(f"Failed to get company contacts: {error_msg}")
                    return False, None, error_msg

            except Exception as e:
                logger.error(f"Failed to get company contacts: {e}")
                return False, None, str(e)

    async def update_resource_provider(
        self,
        resource_id: str,
        company_id: str,
        contact_id: str,
    ) -> tuple[bool, str | None]:
        """
        Update resource provider company and contact via PUT /resources/{resource_id}/administrative.

        Args:
            resource_id: The resource ID
            company_id: The provider company ID
            contact_id: The provider contact ID

        Returns: (success, error_message)
        """
        payload = {
            "data": {
                "type": "resource",
                "id": str(resource_id),
                "relationships": {
                    "providerCompany": {
                        "data": {"type": "company", "id": str(company_id)}
                    },
                    "providerContact": {
                        "data": {"type": "contact", "id": str(contact_id)}
                    },
                },
            }
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.put(
                    f"{self.base_url}/resources/{resource_id}/administrative",
                    json=payload,
                    auth=self.auth,
                    headers=self._get_headers(),
                )

                if response.status_code in (200, 201):
                    logger.info(f"Updated resource {resource_id} provider to company {company_id}, contact {contact_id}")
                    return True, None
                else:
                    error_data = response.json() if response.content else {}
                    error_msg = self._extract_error_message(error_data, response.status_code)
                    logger.warning(f"Failed to update resource provider: {error_msg}")
                    return False, error_msg

            except Exception as e:
                logger.error(f"Failed to update resource provider: {e}")
                return False, str(e)

    async def create_resource_contract(
        self,
        resource_id: str,
        type_of: int,
        start_date: str,
        end_date: str,
        monthly_salary: float | None = None,
        daily_cost: float | None = None,
        parent_contract_id: str | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """
        Create a contract for a resource via POST /contracts.

        Args:
            resource_id: The resource ID (dependsOn)
            type_of: Contract type (0=salarié uses monthly_salary, other uses daily_cost)
            start_date: Contract start date (YYYY-MM-DD)
            end_date: Contract end date (YYYY-MM-DD)
            monthly_salary: Monthly salary (used if typeOf=0)
            daily_cost: Daily production cost (used if typeOf!=0)
            parent_contract_id: Parent contract ID for renewals

        Returns: (success, contract_id, error_message)
        """
        # Build attributes
        attributes: dict[str, Any] = {
            "typeOf": type_of,
            "startDate": start_date,
            "endDate": end_date,
        }

        # Add salary/cost based on typeOf
        if type_of == 0 and monthly_salary is not None:
            attributes["monthlyRemuneration"] = monthly_salary
        elif daily_cost is not None:
            attributes["dailyProductionCost"] = daily_cost

        # Build relationships
        relationships: dict[str, Any] = {
            "dependsOn": {
                "data": {"type": "resource", "id": str(resource_id)}
            }
        }

        # Add parent contract for renewals
        if parent_contract_id:
            relationships["parentContract"] = {
                "data": {"type": "contract", "id": str(parent_contract_id)}
            }

        payload = {
            "data": {
                "type": "contract",
                "attributes": attributes,
                "relationships": relationships,
            }
        }

        logger.info(f"Creating contract for resource {resource_id} with payload: {payload}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/contracts",
                    json=payload,
                    auth=self.auth,
                    headers=self._get_headers(),
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    contract_id = data.get("data", {}).get("id")
                    logger.info(f"Created contract {contract_id} for resource {resource_id}")
                    return True, contract_id, None
                else:
                    error_data = response.json() if response.content else {}
                    error_msg = self._extract_error_message(error_data, response.status_code)
                    logger.warning(f"Failed to create contract: {error_msg}")
                    return False, None, error_msg

            except Exception as e:
                logger.error(f"Failed to create contract: {e}")
                return False, None, str(e)

    def _extract_error_message(
        self,
        error_data: dict[str, Any],
        status_code: int,
    ) -> str:
        """Extract readable error message from API response."""
        if "errors" in error_data and error_data["errors"]:
            errors = error_data["errors"]
            if isinstance(errors, list) and errors:
                first_error = errors[0]
                if isinstance(first_error, dict):
                    title = first_error.get("title", "")
                    detail = first_error.get("detail", "")
                    if detail:
                        return f"{title}: {detail}" if title else detail
                    return title or f"Error {status_code}"
        elif "message" in error_data:
            return error_data["message"]
        return f"API error {status_code}"


# Singleton instance
_client: BoondClient | None = None


def get_boond_client() -> BoondClient:
    """Get the BoondManager client instance."""
    global _client
    if _client is None:
        _client = BoondClient()
    return _client
