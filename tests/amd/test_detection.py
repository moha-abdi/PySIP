from PySIP.amd.tone_detection import square
import unittest


class TestDetection(unittest.TestCase):

    def test_square(self):
        self.assertEqual(4, square(2))


if __name__ == "__main__":
    unittest.main()
