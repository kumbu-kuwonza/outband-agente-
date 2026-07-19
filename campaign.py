from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from livekit import api

from contacts import Contact, load_contacts, update_contact_result

logger = logging.getLogger("outbound-caller.campaign")


async def dial_contact(
    livekit_api: Any,
    room_name: str,
    trunk_id: str,
    contact: Contact,
) -> bool:
    participant_identity = contact.phone

    try:
        await livekit_api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=room_name,
                sip_trunk_id=trunk_id,
                sip_call_to=contact.phone,
                participant_identity=participant_identity,
                wait_until_answered=True,
            )
        )
        logger.info(f"Dialing {contact.name} at {contact.phone}")
        return True
    except Exception as e:
        logger.error(f"Failed to dial {contact.name}: {e}")
        return False


async def run_campaign() -> None:
    contacts = load_contacts()
    if not contacts:
        logger.warning("No contacts found in Google Sheets. Aborting campaign.")
        return

    batch_size = int(os.environ.get("CAMPAIGN_BATCH_SIZE", "10"))
    delay_between_calls = int(os.environ.get("CAMPAIGN_DELAY_BETWEEN_CALLS", "5"))
    trunk_id = os.environ["SIP_OUTBOUND_TRUNK_ID"]

    logger.info(f"Starting campaign with {len(contacts)} contacts (batch={batch_size})")

    livekit_api = api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )

    try:
        for i, contact in enumerate(contacts[:batch_size]):
            logger.info(
                f"Processing contact {i + 1}/{min(batch_size, len(contacts))}: {contact.name}"
            )

            sanitized_phone = re.sub(r"[^a-zA-Z0-9_-]", "", contact.phone)
            room_name = f"prospecting-{sanitized_phone}-{i}"
            try:
                await livekit_api.room.create_room(
                    api.CreateRoomRequest(name=room_name)
                )
                await dial_contact(livekit_api, room_name, trunk_id, contact)
            except Exception as e:
                logger.error(f"Error with contact {contact.name}: {e}")
                update_contact_result(
                    row_index=contact.row_index,
                    result="erro",
                    notes=str(e),
                )
            finally:
                try:
                    await livekit_api.room.delete_room(
                        api.DeleteRoomRequest(room=room_name)
                    )
                except Exception:
                    pass

            if i < min(batch_size, len(contacts)) - 1:
                logger.info(f"Waiting {delay_between_calls}s before next call...")
                await asyncio.sleep(delay_between_calls)
    finally:
        await livekit_api.aclose()

    logger.info("Campaign finished.")
