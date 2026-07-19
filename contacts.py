from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger("outbound-caller.contacts")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@dataclass
class Contact:
    row_index: int
    name: str
    phone: str
    country: str
    business_context: str
    extra: dict[str, Any]

    @classmethod
    def from_row(cls, row_index: int, row: dict[str, str]) -> Contact:
        return cls(
            row_index=row_index,
            name=row.get("Nome", "").strip(),
            phone=row.get("Telefone", "").strip(),
            country=row.get("Pais", "BR").strip().upper(),
            business_context=row.get("Contexto", "").strip(),
            extra={
                k: v
                for k, v in row.items()
                if k not in ("Nome", "Telefone", "Pais", "Contexto")
            },
        )

    @property
    def is_valid(self) -> bool:
        return bool(self.name and self.phone)


def get_worksheet() -> gspread.Worksheet:
    creds_file = os.environ["GOOGLE_SHEETS_CREDENTIALS_FILE"]
    spreadsheet_id = os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"]
    worksheet_name = os.environ.get("GOOGLE_SHEETS_WORKSHEET_NAME", "Contatos")

    creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    return spreadsheet.worksheet(worksheet_name)


def load_contacts() -> list[Contact]:
    worksheet = get_worksheet()
    rows = worksheet.get_all_records()
    contacts = []

    for i, row in enumerate(rows, start=2):
        contact = Contact.from_row(row_index=i, row=row)
        if contact.is_valid:
            contacts.append(contact)
        else:
            logger.warning(
                f"Skipping invalid row {i}: name='{contact.name}', phone='{contact.phone}'"
            )

    logger.info(f"Loaded {len(contacts)} valid contacts from Google Sheets")
    return contacts


def update_contact_result(row_index: int, result: str, notes: str = "") -> None:
    worksheet = get_worksheet()
    try:
        headers = worksheet.row_values(1)
        result_col = (
            headers.index("Resultado") + 1
            if "Resultado" in headers
            else len(headers) + 1
        )
        notes_col = (
            headers.index("Notas") + 1 if "Notas" in headers else len(headers) + 2
        )

        if result_col > len(headers):
            worksheet.update_cell(1, result_col, "Resultado")
        if notes_col > len(headers):
            worksheet.update_cell(1, notes_col, "Notas")

        worksheet.update_cell(row_index, result_col, result)
        if notes:
            worksheet.update_cell(row_index, notes_col, notes)

        logger.info(f"Updated row {row_index}: result={result}")
    except Exception as e:
        logger.error(f"Failed to update row {row_index}: {e}")
