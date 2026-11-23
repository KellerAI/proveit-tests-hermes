class TestTotal(unittest.TestCase):
    def test_original(self):
        self.assertEqual(total(), expected_total())
