from unittest import TestCase

from src.exceptions.account import InvalidTemplateError
from src.services.templates import get_template


class TemplatesTest(TestCase):
    def test_get_merchant_template_returns_15_accounts(self):
        accounts = get_template("merchant")
        self.assertEqual(len(accounts), 15)

    def test_all_templates_include_transfer_and_world(self):
        for name in ("merchant", "customer", "operator", "platform", "baas_customer"):
            accounts = get_template(name)
            codes = [a.code for a in accounts]
            self.assertIn("9.9.998", codes, f"9.9.998 missing in {name}")
            self.assertIn("9.9.999", codes, f"9.9.999 missing in {name}")

    def test_unknown_template_raises_invalid_template_error(self):
        with self.assertRaises(InvalidTemplateError):
            get_template("unknown")

    def test_merchant_template_unique_codes(self):
        accounts = get_template("merchant")
        codes = [a.code for a in accounts]
        self.assertEqual(len(codes), len(set(codes)))

    def test_customer_template_unique_codes(self):
        accounts = get_template("customer")
        codes = [a.code for a in accounts]
        self.assertEqual(len(codes), len(set(codes)))

    def test_operator_template_unique_codes(self):
        accounts = get_template("operator")
        codes = [a.code for a in accounts]
        self.assertEqual(len(codes), len(set(codes)))

    def test_platform_template_unique_codes(self):
        accounts = get_template("platform")
        codes = [a.code for a in accounts]
        self.assertEqual(len(codes), len(set(codes)))

    def test_baas_customer_template_unique_codes(self):
        accounts = get_template("baas_customer")
        codes = [a.code for a in accounts]
        self.assertEqual(len(codes), len(set(codes)))
