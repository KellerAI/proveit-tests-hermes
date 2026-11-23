class TestTotal(unittest.TestCase):
    def test_original(self):
        self.assertEqual(subtotal(), expected_total())
