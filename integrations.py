from __future__ import annotations

import os
import logging
from dataclasses import dataclass, asdict
from typing import Any

import httpx

logger = logging.getLogger("outbound-caller.integrations")


@dataclass
class CallSummary:
    is_decisor: bool
    decisor_name: str
    decisor_phone: str
    appointment_date: str
    contact_person_name: str
    notes: str
    contact_row_index: int
    call_outcome: str

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


async def send_summary_to_n8n(summary: CallSummary) -> bool:
    webhook_url = os.environ.get("N8N_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("N8N_WEBHOOK_URL not set, skipping webhook send")
        return False

    payload = summary.to_payload()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(webhook_url, json=payload)
            response.raise_for_status()
            logger.info(f"n8n webhook sent successfully: {response.status_code}")
            return True
    except httpx.HTTPStatusError as e:
        logger.error(
            f"n8n webhook HTTP error: {e.response.status_code} - {e.response.text}"
        )
        return False
    except httpx.RequestError as e:
        logger.error(f"n8n webhook request error: {e}")
        return False
    except Exception as e:
        logger.error(f"n8n webhook unexpected error: {e}")
        return False
