import unittest

from app.extraction_service import parse_invoice_from_text, _extract_json_from_text


class ExtractionServiceTests(unittest.TestCase):
    def test_parses_line_items_and_totals_from_invoice_text(self):
        text = """Invoice
Vendor: Example Co
Invoice # 1001
Date: 2024-03-15

Description Qty Unit Price Amount
Consulting Services 2 100.00 200.00
Hosting 1 50.00 50.00

Subtotal $250.00
Tax $25.00
Total $275.00
"""

        data = parse_invoice_from_text(text)

        self.assertEqual(data["vendor_name"], "Example Co")
        self.assertEqual(data["invoice_number"], "1001")
        self.assertEqual(data["invoice_date"], "2024-03-15")
        self.assertEqual(len(data["line_items"]), 2)
        self.assertEqual(data["line_items"][0]["description"], "Consulting Services")
        self.assertEqual(data["line_items"][0]["quantity"], 2.0)
        self.assertEqual(data["line_items"][0]["unit_price"], 100.0)
        self.assertEqual(data["line_items"][0]["amount"], 200.0)
        self.assertEqual(data["subtotal"], 250.0)
        self.assertEqual(data["tax"], 25.0)
        self.assertEqual(data["total"], 275.0)

    def test_infers_total_when_not_explicitly_labeled(self):
        text = """Invoice
Vendor: Example Co
Invoice # 1001
Date: 2024-03-15

Consulting Services 2 100.00 200.00
Hosting 1 50.00 50.00

Subtotal $250.00
Tax $25.00
"""

        data = parse_invoice_from_text(text)

        self.assertEqual(data["subtotal"], 250.0)
        self.assertEqual(data["tax"], 25.0)
        self.assertEqual(data["total"], 275.0)

    def test_parses_invoice_items_with_large_amounts(self):
        text = """Invoice
Vendor: Example Co
Invoice # 1001
Date: 2024-03-15

A4 Printing Paper (Ream) 10 300.00 3000.00
Office Chairs 2 4500.00 9000.00

Subtotal Rs. 13,650.00
Tax (18% GST) Rs. 2,457.00
Total Rs. 16,107.00
"""

        data = parse_invoice_from_text(text)

        self.assertEqual(len(data["line_items"]), 2)
        self.assertEqual(data["line_items"][0]["amount"], 3000.0)
        self.assertEqual(data["line_items"][1]["amount"], 9000.0)

    def test_parses_item_descriptions_when_only_names_are_detected(self):
        text = """INVOICE

Item
Printer
Ink Cartridge
A4 Paper Box
USB Cable
Subtotal
GST (18%)
Grand Total
"""

        data = parse_invoice_from_text(text)

        self.assertEqual(len(data["line_items"]), 4)
        self.assertEqual(data["line_items"][0]["description"], "Printer")
        self.assertEqual(data["line_items"][1]["description"], "Ink Cartridge")

    def test_extract_json_from_text_raises_helpful_error_for_invalid_payload(self):
        with self.assertRaisesRegex(ValueError, "Could not parse structured extraction response as JSON"):
            _extract_json_from_text("not-json")


if __name__ == "__main__":
    unittest.main()
