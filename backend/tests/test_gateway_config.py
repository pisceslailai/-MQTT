import unittest

from app.gateway_config import IgnoredMqttPayload, parse_readings_with_configs


class GatewayConfigTests(unittest.TestCase):
    def test_ignores_plain_heartbeat_payload(self) -> None:
        with self.assertRaises(IgnoredMqttPayload):
            parse_readings_with_configs("/USR-G770/update", b"heartbeat")

    def test_rejects_unknown_plain_text_payload_as_parse_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "payload is not JSON"):
            parse_readings_with_configs("/USR-G770/update", b"not-a-json-reading")


if __name__ == "__main__":
    unittest.main()
