from __future__ import annotations

import unittest

from frappe_config_pack.handlers.property_setter import PropertySetterHandler
from frappe_config_pack.tests.helpers import changed_metadata, property_setter


class TestPropertySetterHandler(unittest.TestCase):
    def test_normalizes_semantically_equivalent_property_values(self) -> None:
        handler = PropertySetterHandler()
        string_value = handler.serialize(property_setter())
        integer_document = property_setter()
        integer_document["value"] = 0
        integer_value = handler.serialize(integer_document)
        self.assertEqual(string_value, integer_value)
        self.assertEqual(string_value["identity"], "Sales Invoice.customer.reqd")

    def test_modified_timestamp_does_not_change_output(self) -> None:
        handler = PropertySetterHandler()
        self.assertEqual(handler.serialize(property_setter()), handler.serialize(changed_metadata(property_setter())))
