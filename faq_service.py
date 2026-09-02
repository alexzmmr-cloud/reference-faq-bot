import json
from pathlib import Path

FAQ_PATH = Path(__file__).resolve().parent / "faq.json"

with open(FAQ_PATH, encoding="utf-8") as f:
    FAQ_ITEMS = json.load(f)

FAQ_BY_ID = {item["id"]: item for item in FAQ_ITEMS}


def find_by_id(faq_id: str) -> dict | None:
    return FAQ_BY_ID.get(faq_id)


def find_by_keyword(text: str) -> dict | None:
    text_lower = text.lower()
    for item in FAQ_ITEMS:
        for keyword in item["keywords"]:
            if keyword.lower() in text_lower:
                return item
    return None
