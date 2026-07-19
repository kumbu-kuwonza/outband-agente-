from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from livekit import rtc, api
from livekit.agents import (
    AgentSession,
    Agent,
    JobContext,
    function_tool,
    RunContext,
    get_job_context,
    cli,
    WorkerOptions,
    RoomInputOptions,
)
from livekit.plugins import (
    deepgram,
    openai,
    cartesia,
    silero,
    noise_cancellation,
)

# NOTE: EnglishModel is used for turn detection. For Portuguese calls (BR/PT),
# this could be swapped when LiveKit adds a Portuguese turn detector.
from livekit.plugins.turn_detector.english import EnglishModel

# Configurable turn detection model. Currently English-only.
# For Portuguese calls, swap this when LiveKit adds a Portuguese turn detector.
turn_detection_model = EnglishModel

from contacts import Contact
from integrations import CallSummary, send_summary_to_n8n
from prompts import get_prospecting_prompt
from campaign import run_campaign

load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("outbound-caller")
logger.setLevel(logging.INFO)

outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")


class ProspectingAgent(Agent):
    def __init__(
        self,
        *,
        contact: Contact,
        agent_name: str = "Consultor",
        company_name: str = "MEC Burguer",
    ):
        prompt = get_prospecting_prompt(
            agent_name=agent_name,
            company_name=company_name,
            contact_name=contact.name,
            business_context=contact.business_context,
            country=contact.country,
        )
        super().__init__(instructions=prompt)
        self.contact = contact
        self.participant: rtc.RemoteParticipant | None = None
        self.call_summary: CallSummary | None = None

    def set_participant(self, participant: rtc.RemoteParticipant):
        self.participant = participant

    async def hangup(self):
        job_ctx = get_job_context()
        await job_ctx.api.room.delete_room(
            api.DeleteRoomRequest(room=job_ctx.room.name)
        )

    @function_tool()
    async def end_call(
        self,
        ctx: RunContext,
        is_decisor: bool,
        decisor_name: str,
        decisor_phone: str,
        appointment_date: str,
        contact_person_name: str,
        notes: str,
        call_outcome: str,
    ):
        """Finalize a prospection call with a structured summary.

        Args:
            is_decisor: Whether the contact was the decision maker
            decisor_name: Name of the decision maker if identified
            decisor_phone: Phone of the decision maker if collected
            appointment_date: Scheduled appointment date/time if any
            contact_person_name: Name of the person who answered
            notes: Important observations from the conversation
            call_outcome: One of: agendado, interessado, nao_interessado, nao_decisor, recusou_contato, nao_atendeu
        """
        self.call_summary = CallSummary(
            is_decisor=is_decisor,
            decisor_name=decisor_name,
            decisor_phone=decisor_phone,
            appointment_date=appointment_date,
            contact_person_name=contact_person_name,
            notes=notes,
            contact_row_index=self.contact.row_index,
            call_outcome=call_outcome,
        )

        logger.info(
            f"Call ended for {self.contact.name}: outcome={call_outcome}, "
            f"is_decisor={is_decisor}, appointment={appointment_date}"
        )

        current_speech = ctx.session.current_speech
        if current_speech:
            await current_speech.wait_for_playout()

        await self.hangup()

    @function_tool()
    async def detected_answering_machine(self, ctx: RunContext):
        """Called when the call reaches voicemail. Hang up immediately."""
        logger.info(f"Voicemail detected for {self.contact.name}")
        self.call_summary = CallSummary(
            is_decisor=False,
            decisor_name="",
            decisor_phone="",
            appointment_date="",
            contact_person_name="",
            notes="Caixa de correio detectado",
            contact_row_index=self.contact.row_index,
            call_outcome="nao_atendeu",
        )
        await self.hangup()


async def entrypoint(ctx: JobContext):
    logger.info(f"Connecting to room {ctx.room.name}")
    await ctx.connect()

    dial_info = json.loads(ctx.job.metadata)
    participant_identity = dial_info["phone_number"]

    contact = Contact(
        row_index=dial_info.get("row_index", 0),
        name=dial_info.get("contact_name", "Contato"),
        phone=dial_info["phone_number"],
        country=dial_info.get("country", "BR"),
        business_context=dial_info.get("business_context", ""),
        extra={},
    )

    agent = ProspectingAgent(
        contact=contact,
        agent_name=os.environ.get("AGENT_NAME", "Consultor"),
        company_name=os.environ.get("COMPANY_NAME", "MEC Burguer"),
    )

    session = AgentSession(
        turn_detection=turn_detection_model(),
        vad=silero.VAD.load(),
        stt=deepgram.STT(),
        tts=cartesia.TTS(),
        llm=openai.LLM(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            base_url=os.environ.get("OPENAI_BASE_URL"),
        ),
    )

    session_started = asyncio.create_task(
        session.start(
            agent=agent,
            room=ctx.room,
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVCTelephony(),
            ),
        )
    )

    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=ctx.room.name,
                sip_trunk_id=outbound_trunk_id,
                sip_call_to=participant_identity,
                participant_identity=participant_identity,
                wait_until_answered=True,
            )
        )

        await session_started
        participant = await ctx.wait_for_participant(identity=participant_identity)
        logger.info(f"Participant joined: {participant.identity}")

        agent.set_participant(participant)

    except api.TwirpError as e:
        logger.error(
            f"Error creating SIP participant: {e.message}, "
            f"SIP status: {e.metadata.get('sip_status_code')} "
            f"{e.metadata.get('sip_status')}"
        )
        ctx.shutdown()


async def run_campaign_entrypoint():
    await run_campaign()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "campaign":
        asyncio.run(run_campaign_entrypoint())
    else:
        cli.run_app(
            WorkerOptions(
                entrypoint_fnc=entrypoint,
                agent_name="outbound-caller",
            )
        )
