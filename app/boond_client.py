"""BoondManager API client for REST operations."""

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models import ENTITY_CONFIGS

logger = logging.getLogger(__name__)


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

        return payload

    async def _create_opportunity(
        self,
        title: str,
        contact_id: int | str,
        company_id: int | str,
        main_manager_id: int | str | None = None,
    ) -> tuple[bool, str | None, str | None]:
        """
        Create an opportunity (action) in BoondManager.

        Returns: (success, opportunity_id, error_message)
        """
        payload: dict[str, Any] = {
            "data": {
                "type": "action",
                "attributes": {
                    "title": title,
                    "state": 0,  # En cours
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

        logger.info(f"Creating opportunity with payload: {payload}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/actions",
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
    ) -> tuple[bool, str | None, str | None]:
        """
        Create a won positioning for an opportunity.
        This is required to create projects in modes other than fixed/product.

        Returns: (success, positioning_id, error_message)
        """
        # State 3 = won (gagné) in BoondManager
        payload = {
            "data": {
                "type": "positioning",
                "attributes": {
                    "state": 3,  # Won/Gagné
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
                    logger.info(f"Created won positioning with ID: {positioning_id}")
                    return True, positioning_id, None
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
            resource_id = row_data.get("main_manager_id") or row_data.get("resource_id")
            contact_id = row_data.get("contact_id")
            company_id = row_data.get("company_id")
            title = row_data.get("reference") or "Nouveau projet"

            # If mode is not fixed(1) or product(2), we need positioning
            if mode not in (1, 2, "1", "2"):
                if not resource_id:
                    return False, None, "main_manager_id requis pour créer un positionnement"

                # If no opportunity provided, create one first
                if not opportunity_id:
                    if not contact_id:
                        return False, None, "contact_id requis pour créer une opportunité"
                    if not company_id:
                        return False, None, "company_id requis pour créer une opportunité"

                    logger.info(f"Creating opportunity '{title}' for contact {contact_id}")
                    success, new_opp_id, error = await self._create_opportunity(
                        title, contact_id, company_id, resource_id
                    )
                    if not success:
                        return False, None, f"Erreur création opportunité: {error}"

                    opportunity_id = new_opp_id
                    row_data["opportunity_id"] = opportunity_id
                    logger.info(f"Opportunity created with ID: {opportunity_id}")

                # Create won positioning
                logger.info(f"Creating won positioning for opportunity {opportunity_id}")
                success, pos_id, error = await self._create_won_positioning(
                    opportunity_id, resource_id
                )
                if not success:
                    return False, None, f"Erreur création positionnement: {error}"
                logger.info(f"Won positioning created: {pos_id}")

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
