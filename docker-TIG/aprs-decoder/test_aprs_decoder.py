import unittest

from aprs_decoder import AprsDecoder


class AprsDecoderTests(unittest.TestCase):
    def setUp(self):
        self.decoder = AprsDecoder()
        self.topic = "sonda/lora/aprs/telemetry/EA2FMQ-8"

    def test_configuration_and_compressed_position(self):
        self.assertIsNone(self.decoder.normalize(
            self.topic,
            "EA2FMQ-8>APLRT1,WIDE1-1::EA2FMQ-8 :PARM.Celsius,Atm_Press",
        ))
        self.assertIsNone(self.decoder.normalize(
            self.topic,
            "EA2FMQ-8>APLRT1,WIDE1-1::EA2FMQ-8 :UNIT.C,hPa",
        ))
        self.assertIsNone(self.decoder.normalize(
            self.topic,
            "EA2FMQ-8>APLRT1,WIDE1-1::EA2FMQ-8 :EQNS.0,0.1,-50,0,0.125,0",
        ))
        decoded = self.decoder.normalize(
            self.topic,
            "EA2FMQ-8>APLRT1,WIDE1-1:=/9H)9N:jMO!!Q|*W)gx@|",
        )
        self.assertIsNotNone(decoded)
        output_topic, payload = decoded
        self.assertEqual(output_topic, "sonda/lora/EA2FMQ-8/telemetry")
        self.assertEqual(payload["status"], "aprs")
        self.assertIn("lat", payload)
        self.assertIn("lng", payload)
        self.assertAlmostEqual(payload["temperature_c"], 29.8)
        self.assertAlmostEqual(payload["pressure_hpa"], 993.5)
        self.assertNotIn("aprs_channel_3", payload)


if __name__ == "__main__":
    unittest.main()
