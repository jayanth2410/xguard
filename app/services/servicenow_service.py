"""ServiceNow Integration Service"""
from typing import Optional, Dict, Any, List
from enum import Enum
import httpx
import structlog
from app.core.config import settings

logger = structlog.get_logger()


class SNTableType(str, Enum):
    """ServiceNow table types"""
    INCIDENT = "incident"
    CHANGE_REQUEST = "change_request"
    REQUEST = "sc_request"


class ServiceNowService:
    """Service for integrating with ServiceNow"""

    def __init__(self):
        self.instance = settings.SERVICENOW_INSTANCE.rstrip('/') if settings.SERVICENOW_INSTANCE else ''
        self.username = settings.SERVICENOW_USERNAME
        self.password = settings.SERVICENOW_PASSWORD
        self.incident_table = settings.SERVICENOW_INCIDENT_TABLE
        self.change_table = settings.SERVICENOW_CHANGE_TABLE
        self.request_table = settings.SERVICENOW_REQUEST_TABLE
        self.approval_field = settings.SERVICENOW_APPROVAL_FIELD
        self.enabled = settings.SERVICENOW_ENABLED

    def _get_table_name(self, table_type: SNTableType) -> str:
        """Get actual table name from type"""
        if table_type == SNTableType.INCIDENT:
            return self.incident_table
        elif table_type == SNTableType.CHANGE_REQUEST:
            return self.change_table
        elif table_type == SNTableType.REQUEST:
            return self.request_table
        return self.incident_table

    def _get_auth(self) -> tuple:
        """Get authentication tuple"""
        return (self.username, self.password)

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers"""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to ServiceNow"""
        if not self.enabled:
            return {"success": False, "error": "ServiceNow integration is disabled in config"}

        if not self.instance:
            return {"success": False, "error": "ServiceNow instance URL is not configured"}

        if not self.instance.startswith(('http://', 'https://')):
            return {"success": False, "error": f"Invalid ServiceNow URL: {self.instance}"}

        try:
            url = f"{self.instance}/api/now/table/{self.incident_table}?sysparm_limit=1"
            logger.info("servicenow_testing_connection", url=url, username=self.username)

            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.get(
                    url,
                    auth=self._get_auth(),
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    logger.info("servicenow_connection_success", instance=self.instance)
                    return {"success": True, "message": f"Connected to {self.instance}"}
                elif response.status_code == 401:
                    return {"success": False, "error": "Authentication failed - check username/password"}
                else:
                    logger.error("servicenow_connection_failed", status=response.status_code, body=response.text[:200])
                    return {"success": False, "error": f"HTTP {response.status_code}: {response.text[:100]}"}

        except Exception as e:
            logger.exception("servicenow_connection_error", error=str(e))
            return {"success": False, "error": str(e)}

    async def get_record(
        self,
        number: str,
        table_type: SNTableType = SNTableType.INCIDENT
    ) -> Optional[Dict[str, Any]]:
        """Get record by number from specified table"""
        if not self.enabled:
            return None

        table = self._get_table_name(table_type)

        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.get(
                    f"{self.instance}/api/now/table/{table}",
                    params={"sysparm_query": f"number={number}", "sysparm_display_value": "true"},
                    auth=self._get_auth(),
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    data = response.json()
                    results = data.get("result", [])
                    if results:
                        logger.info("servicenow_record_found", number=number, table=table)
                        return results[0]
                    return None
                else:
                    logger.error("servicenow_get_record_failed", status=response.status_code)
                    return None

        except Exception as e:
            logger.exception("servicenow_get_record_error", error=str(e))
            return None

    async def get_records(
        self,
        table_type: SNTableType = SNTableType.INCIDENT,
        query: str = "",
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get list of records from specified table"""
        if not self.enabled:
            return []

        table = self._get_table_name(table_type)

        try:
            # Default sort by most recent
            full_query = query
            if "ORDERBY" not in query.upper():
                if query:
                    full_query = f"{query}^ORDERBYDESCsys_created_on"
                else:
                    full_query = "ORDERBYDESCsys_created_on"

            params = {
                "sysparm_limit": limit,
                "sysparm_offset": offset,
                "sysparm_display_value": "true",
                "sysparm_query": full_query
            }

            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.get(
                    f"{self.instance}/api/now/table/{table}",
                    params=params,
                    auth=self._get_auth(),
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("result", [])
                else:
                    logger.error("servicenow_get_records_failed", status=response.status_code)
                    return []

        except Exception as e:
            logger.exception("servicenow_get_records_error", error=str(e))
            return []

    # Convenience methods for specific tables
    async def get_incident(self, incident_number: str) -> Optional[Dict[str, Any]]:
        """Get incident by number"""
        return await self.get_record(incident_number, SNTableType.INCIDENT)

    async def get_incidents(self, query: str = "", limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get list of incidents - sorted by most recent"""
        if query and "ORDERBY" not in query.upper():
            query = f"{query}^ORDERBYDESCsys_created_on"
        elif not query:
            query = "ORDERBYDESCsys_created_on"
        return await self.get_records(SNTableType.INCIDENT, query, limit, offset)

    async def get_change_request(self, change_number: str) -> Optional[Dict[str, Any]]:
        """Get change request by number"""
        return await self.get_record(change_number, SNTableType.CHANGE_REQUEST)

    async def get_change_requests(self, query: str = "", limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get list of change requests - sorted by most recent"""
        if query and "ORDERBY" not in query.upper():
            query = f"{query}^ORDERBYDESCsys_created_on"
        elif not query:
            query = "ORDERBYDESCsys_created_on"
        return await self.get_records(SNTableType.CHANGE_REQUEST, query, limit, offset)

    async def get_request(self, request_number: str) -> Optional[Dict[str, Any]]:
        """Get service request by number"""
        return await self.get_record(request_number, SNTableType.REQUEST)

    async def get_requests(self, query: str = "", limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get list of service requests"""
        return await self.get_records(SNTableType.REQUEST, query, limit, offset)

    async def get_pending_changes(self) -> List[Dict[str, Any]]:
        """Get change requests pending approval"""
        query = "state=1^ORstate=-5"  # New or Assess state
        return await self.get_change_requests(query=query)

    async def get_pending_incidents(self) -> List[Dict[str, Any]]:
        """Get incidents pending action"""
        query = "state=1^ORstate=2"  # New or In Progress
        return await self.get_incidents(query=query)

    async def update_record(
        self,
        sys_id: str,
        update_data: Dict[str, Any],
        table_type: SNTableType = SNTableType.INCIDENT
    ) -> Optional[Dict[str, Any]]:
        """Update a record"""
        if not self.enabled:
            return None

        table = self._get_table_name(table_type)

        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.patch(
                    f"{self.instance}/api/now/table/{table}/{sys_id}",
                    json=update_data,
                    auth=self._get_auth(),
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info("servicenow_record_updated", sys_id=sys_id, table=table)
                    return data.get("result")
                else:
                    logger.error("servicenow_update_failed", status=response.status_code)
                    return None

        except Exception as e:
            logger.exception("servicenow_update_error", error=str(e))
            return None

    async def add_work_notes(
        self,
        sys_id: str,
        notes: str,
        table_type: SNTableType = SNTableType.INCIDENT
    ) -> Optional[Dict[str, Any]]:
        """Add work notes to a record"""
        return await self.update_record(sys_id, {"work_notes": notes}, table_type)

    async def update_approval_status(
        self,
        sys_id: str,
        status: str,
        notes: str = "",
        table_type: SNTableType = SNTableType.CHANGE_REQUEST
    ) -> Optional[Dict[str, Any]]:
        """Update approval status of a record"""
        update_data = {
            self.approval_field: status
        }
        if notes:
            update_data["work_notes"] = notes

        return await self.update_record(sys_id, update_data, table_type)

    async def create_change_request(
        self,
        short_description: str,
        description: str = "",
        category: str = "Other",
        priority: str = "3",
        risk: str = "moderate",
        impact: str = "medium",
        assignment_group: str = "",
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Create a new change request"""
        if not self.enabled:
            return None

        try:
            data = {
                "short_description": short_description,
                "description": description,
                "category": category,
                "priority": priority,
                "risk": risk,
                "impact": impact,
                "assignment_group": assignment_group or settings.SERVICENOW_ASSIGNMENT_GROUP,
                "type": "normal",
                **kwargs
            }

            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                response = await client.post(
                    f"{self.instance}/api/now/table/{self.change_table}",
                    json=data,
                    auth=self._get_auth(),
                    headers=self._get_headers()
                )

                if response.status_code in [200, 201]:
                    result = response.json().get("result")
                    logger.info("servicenow_change_created", number=result.get("number"))
                    return result
                else:
                    logger.error("servicenow_create_failed", status=response.status_code, body=response.text[:200])
                    return None

        except Exception as e:
            logger.exception("servicenow_create_error", error=str(e))
            return None

    def parse_record_to_work_package(
        self,
        record: Dict[str, Any],
        record_type: str = "incident"
    ) -> Dict[str, Any]:
        """Parse ServiceNow record to work package format"""
        trigger_source = f"servicenow_{record_type}"

        return {
            "ticket_id": record.get("number", ""),
            "title": record.get("short_description", ""),
            "description": record.get("description", ""),
            "trigger_source": trigger_source,
            "servicenow_sys_id": record.get("sys_id", ""),
            "priority": record.get("priority", "3"),
            "category": record.get("category", ""),
            "assignment_group": record.get("assignment_group", {}).get("display_value", "") if isinstance(record.get("assignment_group"), dict) else record.get("assignment_group", ""),
            "risk": record.get("risk", ""),
            "impact": record.get("impact", ""),
        }

    async def close_ticket(
        self,
        ticket_number: str,
        close_notes: str = "",
        close_code: str = "Successful"
    ) -> Dict[str, Any]:
        """Move a ServiceNow ticket to Review status after execution"""
        if not self.enabled:
            return {"success": False, "error": "ServiceNow integration is disabled"}

        # Determine ticket type and get record
        if ticket_number.startswith("CHG"):
            record = await self.get_change_request(ticket_number)
            table_type = SNTableType.CHANGE_REQUEST
            # State 0 = Review for Change Requests
            close_data = {
                "state": "0",  # Review state for changes
                "work_notes": close_notes or "Change implemented via Maker-Checker platform. Ready for review."
            }
        elif ticket_number.startswith("INC"):
            record = await self.get_incident(ticket_number)
            table_type = SNTableType.INCIDENT
            # State 6 = Resolved (acts as review before close) for Incidents
            close_data = {
                "state": "6",  # Resolved state for incidents (pending user confirmation)
                "resolution_notes": close_notes or "Resolved via Maker-Checker platform. Pending review.",
                "resolution_code": close_code
            }
        elif ticket_number.startswith("REQ"):
            record = await self.get_request(ticket_number)
            table_type = SNTableType.REQUEST
            close_data = {
                "request_state": "closed_complete",
                "work_notes": close_notes or "Request completed via Maker-Checker platform"
            }
        else:
            return {"success": False, "error": f"Unknown ticket type: {ticket_number}"}

        if not record:
            return {"success": False, "error": f"Ticket not found: {ticket_number}"}

        sys_id = record.get("sys_id")
        if not sys_id:
            return {"success": False, "error": "Could not get sys_id for ticket"}

        result = await self.update_record(sys_id, close_data, table_type)

        if result:
            logger.info("servicenow_ticket_to_review", ticket_number=ticket_number)
            return {
                "success": True,
                "ticket_number": ticket_number,
                "message": f"Ticket {ticket_number} moved to Review status"
            }
        else:
            return {"success": False, "error": f"Failed to update ticket {ticket_number}"}

    async def add_execution_log(
        self,
        ticket_number: str,
        execution_log: str
    ) -> Dict[str, Any]:
        """Add execution log as work notes to ServiceNow ticket"""
        if not self.enabled:
            return {"success": False, "error": "ServiceNow integration is disabled"}

        # Determine ticket type and get record
        if ticket_number.startswith("CHG"):
            record = await self.get_change_request(ticket_number)
            table_type = SNTableType.CHANGE_REQUEST
        elif ticket_number.startswith("INC"):
            record = await self.get_incident(ticket_number)
            table_type = SNTableType.INCIDENT
        elif ticket_number.startswith("REQ"):
            record = await self.get_request(ticket_number)
            table_type = SNTableType.REQUEST
        else:
            return {"success": False, "error": f"Unknown ticket type: {ticket_number}"}

        if not record:
            return {"success": False, "error": f"Ticket not found: {ticket_number}"}

        sys_id = record.get("sys_id")
        result = await self.add_work_notes(sys_id, execution_log, table_type)

        if result:
            return {"success": True, "message": "Execution log added to ticket"}
        else:
            return {"success": False, "error": "Failed to add execution log"}


# Singleton instance
servicenow = ServiceNowService()
