# Outbound Prospector Agent

AI agent for automated outbound prospecting calls using LiveKit, Twilio SIP, Google Sheets, and n8n.

## Features

- Reads contacts from Google Sheets
- Makes outbound calls via LiveKit + Twilio SIP trunk
- Uses LLM (OpenAI-compatible) for natural conversation
- Detects voicemail and handles gracefully
- Verifies decision maker status
- Attempts appointment scheduling
- Sends structured call summaries to n8n webhook
- Updates Google Sheets with call results
- Supports batch campaign mode

## Prerequisites

- LiveKit server (self-hosted or cloud)
- Twilio account with SIP trunk configured
- Google Sheets API credentials (service account)
- n8n instance with webhook endpoint
- Deepgram API key (STT)
- Cartesia API key (TTS)
- OpenAI-compatible API key (LLM)

## Setup

1. Clone and install:
```bash
git clone <repo-url>
cd outbound-caller-python
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
python agent.py download-files
```

2. Copy `.env.example` to `.env.local` and fill in your credentials.

3. Prepare Google Sheets:
   - Create a spreadsheet with columns: `Nome`, `Telefone`, `Pais`, `Contexto`
   - Share it with the service account email from your credentials.json
   - Optional columns: any extra columns will be stored as context

4. Create n8n webhook:
   - Add a webhook node in n8n
   - Set the URL in `N8N_WEBHOOK_URL`
   - Payload: `{ is_decisor, decisor_name, decisor_phone, appointment_date, contact_person_name, notes, call_outcome, contact_row_index }`

## Running

### As a worker (receives dispatches):
```bash
python agent.py dev
```

### Run campaign mode (reads sheets and dials sequentially):
```bash
python agent.py campaign
```

### Dispatch a single call:
```bash
lk dispatch create \
  --new-room \
  --agent-name outbound-caller \
  --metadata '{"phone_number": "+5511999999999", "contact_name": "João", "country": "BR", "business_context": "Restaurante", "row_index": 2}'
```

## Google Sheets Format

| Nome | Telefone | Pais | Contexto |
|------|----------|------|----------|
| João Silva | +5511999999999 | BR | Dono de restaurante, interessado em delivery |
| Maria Santos | +351912345678 | PT | Gerente de loja, precisa de solução de marketing |

## Environment Variables

See `.env.example` for the full list. Key variables:

- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` — LiveKit connection
- `SIP_OUTBOUND_TRUNK_ID` — SIP trunk for outbound calls
- `GOOGLE_SHEETS_CREDENTIALS_FILE`, `GOOGLE_SHEETS_SPREADSHEET_ID` — Contact source
- `N8N_WEBHOOK_URL` — Where to send call summaries
- `OPENAI_API_KEY`, `OPENAI_MODEL` — LLM provider
