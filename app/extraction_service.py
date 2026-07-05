import os
import re
import json
import logging
import subprocess
import urllib.request
from urllib.error import HTTPError, URLError
from dotenv import load_dotenv

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

load_dotenv()
logger = logging.getLogger(__name__)


def normalize_number(value: str):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_date_string(value: str):
    if not value:
        return None
    value = value.strip()

    match = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", value)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    match = re.match(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", value)
    if match:
        month, day, year = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    return None


def find_first_nonempty_line(text: str):
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned:
            return cleaned
    return None


def find_text_by_patterns(text: str, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match and match.group(1):
            return match.group(1).strip()
    return None


def _normalize_money(value: str):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _looks_like_item_description(cleaned: str) -> bool:
    if not cleaned:
        return False
    if cleaned.lower() in {"item", "items"}:
        return False
    if re.search(r"\b(subtotal|tax|total|gst|grand total|invoice|description|qty|quantity|unit price|amount|thank you|bill to|ship to|from|date)\b", cleaned, re.IGNORECASE):
        return False
    if re.fullmatch(r"[-\d.,$Rs()/%]+", cleaned):
        return False
    return any(ch.isalpha() for ch in cleaned) and len(cleaned.split()) <= 6


def parse_line_items_from_text(text: str):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items = []

    for line in lines:
        lower = line.lower()
        if "description" in lower and ("qty" in lower or "quantity" in lower):
            continue
        if re.search(r"\b(subtotal|tax|total|amount due|balance due|invoice|vendor|date|bill to|ship to)\b", line, re.IGNORECASE):
            continue

        cleaned = re.sub(r"\s+", " ", line).strip()
        if not cleaned:
            continue

        parts = [part.strip() for part in re.split(r"\s{2,}|\t|\|", cleaned) if part.strip()]
        description = None
        qty_text = None
        price_text = None
        amount_text = None

        if len(parts) >= 4:
            description = parts[0]
            qty_text = parts[1]
            price_text = parts[2]
            amount_text = parts[3]
        else:
            # Handle OCR layouts where a product line may contain only quantity, unit price, and amount
            # in a compact form such as: "Keyboard 2 1000 2000" or "50000 100000"
            match = re.match(
                r"^(?P<description>.+?)\s+(?P<quantity>-?\d+(?:\.\d+)?)\s*(?:x|X|@)?\s*\$?(?P<unit_price>-?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?)\s+\$?(?P<amount>-?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?)$",
                cleaned,
            )
            if not match:
                # Fallback for very short OCR lines where the description is missing and only numeric fields remain.
                numeric_parts = re.findall(r"-?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?", cleaned)
                if len(numeric_parts) >= 3:
                    qty_text = numeric_parts[0]
                    price_text = numeric_parts[-2]
                    amount_text = numeric_parts[-1]
                    description = "Item"
                    if _normalize_money(amount_text) is None or _normalize_money(price_text) is None:
                        qty_text = numeric_parts[0]
                        price_text = numeric_parts[1]
                        amount_text = numeric_parts[2]
                elif _looks_like_item_description(cleaned):
                    description = cleaned
            else:
                description = match.group("description").strip()
                qty_text = match.group("quantity")
                price_text = match.group("unit_price")
                amount_text = match.group("amount")

        if not description and _looks_like_item_description(cleaned):
            description = cleaned

        quantity = _normalize_money(qty_text) if qty_text is not None else None
        unit_price = _normalize_money(price_text) if price_text is not None else None
        amount = _normalize_money(amount_text) if amount_text is not None else None
        if amount is None and quantity is not None and unit_price is not None:
            amount = quantity * unit_price

        if not description:
            continue

        if description and quantity is None and unit_price is None and amount is None and not _looks_like_item_description(description):
            continue

        # Avoid creating bogus line items from OCR fragments that are clearly just noise.
        if description == "Item" and quantity is not None and unit_price is not None and amount is not None:
            if amount <= 0 or unit_price <= 0:
                continue

        items.append(
            {
                "description": description,
                "quantity": quantity,
                "unit_price": unit_price,
                "amount": amount,
            }
        )

    return items


def extract_text_with_tesseract(image_path: str) -> str:
    if Image is None or pytesseract is None:
        raise RuntimeError(
            "Tesseract OCR support is not installed. Install pytesseract and make sure the Tesseract binary is available on your PATH."
        )

    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd.strip()

    if not os.path.exists(image_path):
        raise RuntimeError(f"Image file not found: {image_path}")

    with Image.open(image_path) as image_file:
        return pytesseract.image_to_string(image_file)


def parse_invoice_from_text(text: str) -> dict:
    vendor_name = find_text_by_patterns(
        text,
        [
            r"vendor[:\s]*([A-Za-z0-9 &.,-]+)",
            r"bill to[:\s]*([A-Za-z0-9 &.,-]+)",
            r"from[:\s]*([A-Za-z0-9 &.,-]+)",
        ],
    )

    invoice_number = find_text_by_patterns(
        text,
        [
            r"invoice\s*number[:\s]*([A-Za-z0-9-]+)",
            r"inv\s*#[:\s]*([A-Za-z0-9-]+)",
            r"invoice\s*#[:\s]*([A-Za-z0-9-]+)",
        ],
    )

    invoice_date = normalize_date_string(
        find_text_by_patterns(
            text,
            [
                r"invoice\s*date[:\s]*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})",
                r"date[:\s]*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})",
                r"date[:\s]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})",
            ],
        )
    )

    due_date = normalize_date_string(
        find_text_by_patterns(
            text,
            [
                r"due\s*date[:\s]*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})",
                r"due[:\s]*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2})",
                r"due\s*date[:\s]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{4})",
            ],
        )
    )

    subtotal = None
    tax = None
    total = None

    for line in text.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if "subtotal" in lower:
            match = re.search(r"\$?([0-9,]+\.[0-9]{2})", cleaned)
            if match:
                subtotal = normalize_number(match.group(1))
        elif "tax" in lower:
            match = re.search(r"\$?([0-9,]+\.[0-9]{2})", cleaned)
            if match:
                tax = normalize_number(match.group(1))
        elif "total" in lower or "amount due" in lower or "balance due" in lower:
            match = re.search(r"\$?([0-9,]+\.[0-9]{2})", cleaned)
            if match:
                total = normalize_number(match.group(1))

    if total is None and subtotal is not None and tax is not None:
        total = subtotal + tax
    elif total is None:
        items = parse_line_items_from_text(text)
        if items:
            line_total = sum(item.get("amount") or 0.0 for item in items)
            if line_total:
                total = line_total

    return {
        "vendor_name": vendor_name or find_first_nonempty_line(text),
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "line_items": parse_line_items_from_text(text),
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
    }


def _extract_json_from_text(text: str) -> dict:
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError as inner_exc:
                raise ValueError(f"Could not parse structured extraction response as JSON: {inner_exc.msg}") from inner_exc
        raise ValueError(f"Could not parse structured extraction response as JSON: {exc.msg}") from exc


def extract_with_ollama(text: str) -> dict:
    model = os.getenv("OLLAMA_MODEL", "llama3:latest").strip()
    prompt = (
        "Extract invoice fields from the OCR text below and return JSON with keys: "
        "vendor_name, invoice_number, invoice_date, due_date, line_items, subtotal, tax, total. "
        "Line items should be an array of objects with description, quantity, unit_price, amount. "
        "Return only valid JSON.\n\nOCR TEXT:\n"
        + text
    )

    logger.info("Calling Ollama structured extraction with model '%s'", model)
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Ollama is not installed or not available on PATH.") from exc

    if result.returncode != 0:
        error_msg = result.stderr.decode("utf-8", errors="replace").strip() or "Ollama extraction failed"
        logger.error("Ollama extraction failed: %s", error_msg)
        raise RuntimeError(error_msg)

    output = result.stdout.decode("utf-8", errors="replace").strip()
    try:
        return _extract_json_from_text(output)
    except Exception as exc:
        logger.error("Ollama returned an unparsable response: %s", exc)
        raise RuntimeError(f"Ollama returned an unparsable response: {exc}") from exc


def extract_with_provider(text: str, provider: str, api_key: str | None = None) -> dict:
    provider = provider.strip().lower()
    prompt = (
        "Extract invoice fields from the OCR text below and return JSON with keys: "
        "vendor_name, invoice_number, invoice_date, due_date, line_items, subtotal, tax, total. "
        "Line items should be an array of objects with description, quantity, unit_price, amount. "
        "Return only valid JSON.\n\nOCR TEXT:\n"
        + text
    )

    if provider == "gemini":
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add a valid Gemini API key to the .env file to use the Gemini extractor.")

        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        body = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}]
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        logger.info("Calling Gemini API with model '%s'", model)
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            message = f"Gemini API request failed ({exc.code}): {error_text}"
            logger.error(message)
            raise RuntimeError(message) from exc
        except URLError as exc:
            message = f"Gemini API request failed: {exc}"
            logger.error(message)
            raise RuntimeError(message) from exc

        try:
            text_out = payload["candidates"][0]["content"]["parts"][0]["text"]
            return _extract_json_from_text(text_out)
        except Exception as exc:
            message = f"Gemini returned an unparsable response: {exc}"
            logger.error(message)
            raise RuntimeError(message) from exc

    if provider == "perplexity":
        if not api_key:
            api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            raise RuntimeError("PERPLEXITY_API_KEY is not set")
        url = "https://api.perplexity.ai/chat/completions"
        body = json.dumps({
            "model": "llama-3.1-sonar-small-128k-online",
            "messages": [{"role": "system", "content": "You extract invoice data into JSON."}, {"role": "user", "content": prompt}]
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text_out = payload["choices"][0]["message"]["content"]
        return _extract_json_from_text(text_out)

    raise ValueError(f"Unsupported cloud provider: {provider}")


def extract_invoice_data(image_path: str) -> dict:
    provider = os.getenv("EXTRACTION_PROVIDER", "tesseract").strip().lower()

    logger.info("Invoking OCR extraction for %s", image_path)
    text = extract_text_with_tesseract(image_path)
    logger.info("OCR extraction complete. OCR text length: %d chars", len(text))

    parsed = parse_invoice_from_text(text)

    if not parsed.get("line_items"):
        logger.warning("No line items were parsed from the OCR text; the invoice layout may be different or the OCR may be too sparse.")
    if parsed.get("subtotal") is None and parsed.get("tax") is None and parsed.get("total") is None:
        logger.warning("No subtotal/tax/total values were parsed from the OCR text; financial totals remain empty.")

    if provider in {"gemini", "perplexity"}:
        try:
            logger.info("Using %s for structured extraction (fresh request per upload).", provider)
            llm_data = extract_with_provider(text, provider)
            parsed.update({k: v for k, v in llm_data.items() if v is not None})
            logger.info("Structured extraction completed with %d line items and totals=%s/%s/%s", len(parsed.get("line_items", [])), parsed.get("subtotal"), parsed.get("tax"), parsed.get("total"))
            return parsed
        except Exception as exc:
            logger.error("Structured extraction failed for provider '%s': %s", provider, exc)
            logger.warning("Falling back to local parser because the provider response could not be used.")
            return parsed

    if provider == "llm":
        try:
            logger.info("Using local Ollama LLM for structured extraction...")
            llm_data = extract_with_ollama(text)
            parsed.update({k: v for k, v in llm_data.items() if v is not None})
            logger.info("Structured extraction completed with %d line items and totals=%s/%s/%s", len(parsed.get("line_items", [])), parsed.get("subtotal"), parsed.get("tax"), parsed.get("total"))
            return parsed
        except Exception as exc:
            logger.error("Ollama extraction failed: %s", exc)
            logger.warning("Falling back to local parser because the LLM response could not be used.")
            return parsed

    if provider == "tesseract":
        return parsed

    raise ValueError(f"Unsupported extraction provider: {provider}. Supported values are 'tesseract', 'llm', 'gemini', or 'perplexity'.")
