from __future__ import annotations

import unittest

from frappe_config_pack.core.compatibility import check_version_compatibility


class TestVersionCompatibility(unittest.TestCase):
	def test_compares_numeric_version_components_semantically(self) -> None:
		self.assertFalse(check_version_compatibility("15.9.0", ">=15.10").satisfied)
		self.assertTrue(check_version_compatibility("15.10.0", ">=15.10").satisfied)

	def test_rejects_invalid_constraints_and_unavailable_versions(self) -> None:
		self.assertFalse(check_version_compatibility("15.0.0", "not a constraint").satisfied)
		self.assertFalse(check_version_compatibility(None, ">=15,<17").satisfied)
