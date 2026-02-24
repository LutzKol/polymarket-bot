import unittest
from datetime import datetime, timezone

from phase2_pipeline.time_utils import seconds_remaining_in_5m_window


class TestTimeUtils(unittest.TestCase):
    def test_seconds_remaining_boundary(self):
        ts = datetime.fromtimestamp(1700000000 - (1700000000 % 300), tz=timezone.utc)
        self.assertEqual(seconds_remaining_in_5m_window(ts), 300.0)

    def test_seconds_remaining_mid_bucket(self):
        base = 1700000000 - (1700000000 % 300)
        ts = datetime.fromtimestamp(base + 10, tz=timezone.utc)
        self.assertEqual(seconds_remaining_in_5m_window(ts), 290.0)


if __name__ == "__main__":
    unittest.main()
