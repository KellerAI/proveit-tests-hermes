class TestTotal(unittest.TestCase):
    def test_renamed(self):
        self.assertEqual(total(), expected_total())
