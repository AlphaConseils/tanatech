# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestClientCode(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {"name": "Client Code Test Co", "prefix_sequence": "TCC"}
        )
        cls.other_company = cls.env["res.company"].create(
            {"name": "Client Code Other Co", "prefix_sequence": "TCO"}
        )
        cls.Partner = cls.env["res.partner"]
        cls.sequence = cls.Partner._get_sequence_for_company(cls.company.id)

    def _create_partner(self, name, company=None, **extra_values):
        values = {"name": name, "company_id": (company or self.company).id}
        values.update(extra_values)
        return self.Partner.create(values)

    def _number_next(self, sequence):
        sequence.invalidate_recordset(["number_next_actual"])
        return sequence.number_next_actual

    def test_codes_follow_the_company_sequence(self):
        first = self._create_partner("First")
        second = self._create_partner("Second")
        self.assertEqual(first.client_code, "TCC00001")
        self.assertEqual(second.client_code, "TCC00002")
        self.assertEqual(self._number_next(self.sequence), 3)

    def test_batch_create_reserves_distinct_codes(self):
        partners = self.Partner.create(
            [{"name": f"Batch {index}", "company_id": self.company.id} for index in range(3)]
        )
        self.assertEqual(
            partners.mapped("client_code"), ["TCC00001", "TCC00002", "TCC00003"]
        )

    def test_existing_codes_are_skipped(self):
        self._create_partner("Manual", client_code="TCC00001")
        self._create_partner("Manual too", client_code="TCC00002")
        generated = self._create_partner("Generated")
        self.assertEqual(generated.client_code, "TCC00003")

    def test_number_helpers_ignore_placeholders_and_honour_minimum(self):
        self._create_partner("One", client_code="TCC00001")
        self._create_partner("Five", client_code="TCC00005")
        self._create_partner("Placeholder", client_code="__TMP__42")
        self._create_partner("Alpha suffix", client_code="TCC00ABC")

        numbers = self.Partner._get_all_existing_client_code_numbers("TCC")
        self.assertEqual(numbers, {1, 5})
        self.assertEqual(
            self.Partner._get_all_existing_client_code_numbers("TCC", minimum=2), {5}
        )
        self.assertEqual(self.Partner._get_max_client_code_number("TCC"), 5)
        self.assertEqual(self.Partner._get_max_client_code_number("ZZZ"), 0)
        self.assertEqual(
            self.Partner._get_existing_client_code_numbers("TCC", self.company.id),
            {1, 5},
        )

    def test_realign_moves_sequence_past_highest_code(self):
        self._create_partner("High", client_code="TCC00040")
        self.Partner._realign_client_code_sequence(self.company.id)
        self.assertEqual(self._number_next(self.sequence), 41)
        self.assertEqual(self._create_partner("Next").client_code, "TCC00041")

    def test_company_change_assigns_code_from_new_company(self):
        partner = self._create_partner("Mover")
        self.assertEqual(partner.client_code, "TCC00001")
        partner.write({"company_id": self.other_company.id})
        self.assertEqual(partner.client_code, "TCO00001")
        other_sequence = self.Partner._get_sequence_for_company(self.other_company.id)
        self.assertEqual(self._number_next(other_sequence), 2)

    def test_next_sequence_code_moves_the_sequence(self):
        code = self.Partner._get_next_sequence_client_code(self.company.id)
        self.assertEqual(code, "TCC00001")
        self.assertEqual(self._number_next(self.sequence), 2)
