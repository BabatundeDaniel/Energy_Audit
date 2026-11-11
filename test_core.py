import json
import threading
import unittest
import urllib.error
import urllib.request

import app
import energy_core as core


def sample(**over):
    p = {"machines": [{"name": "Motor", "power_watts": 1000, "hours_per_day": 10,
                       "quantity": 1, "load_factor": 1, "days_per_month": 30}],
         "settings": {"tariff": 100}}
    p["settings"].update(over)
    return p


class CoreTests(unittest.TestCase):
    def test_grid_only(self):
        r = core.calculate_from_payload(sample())
        self.assertAlmostEqual(r["totals"]["kwh_day"], 10)
        self.assertAlmostEqual(r["totals"]["kwh_month"], 300)
        self.assertAlmostEqual(r["totals"]["cost_month"], 30000)

    def test_generator_mix(self):
        r = core.calculate_from_payload(sample(generator_share=50, diesel_price=1500, kwh_per_litre=3))
        # 150 kWh grid @100 + 150 kWh gen @500 = 15000 + 75000
        self.assertAlmostEqual(r["totals"]["cost_month"], 90000)
        self.assertAlmostEqual(r["totals"]["diesel_litres"], 50)

    def test_quantity_and_load_factor(self):
        p = sample()
        p["machines"][0].update(quantity=4, load_factor=0.5)
        self.assertAlmostEqual(core.calculate_from_payload(p)["totals"]["kwh_day"], 20)

    def test_scenario(self):
        r = core.calculate_from_payload(sample(efficiency_gain=20, solar_share=50))
        self.assertAlmostEqual(r["scenario"]["kwh_month"], 300 * 0.8 * 0.5)
        self.assertAlmostEqual(r["scenario"]["saving_month"], 30000 - 12000)

    def test_validation(self):
        bad = [
            {"machines": []},
            {"machines": "x"},
            sample(tariff=0),
            sample(generator_share=120),
        ]
        for p in bad:
            with self.assertRaises(core.ValidationError):
                core.calculate_from_payload(p)
        p = sample(); p["machines"][0]["hours_per_day"] = 25
        with self.assertRaises(core.ValidationError):
            core.calculate_from_payload(p)
        p = sample(); p["machines"][0]["power_watts"] = "abc"
        with self.assertRaises(core.ValidationError):
            core.calculate_from_payload(p)

    def test_csv_injection_guard(self):
        p = sample(); p["machines"][0]["name"] = "=HYPERLINK(1)"
        csv_text = core.to_csv(core.calculate_from_payload(p), "+evil")
        self.assertIn("'=HYPERLINK(1)", csv_text)
        self.assertIn("'+evil", csv_text)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = app.make_server("127.0.0.1", 0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def post(self, path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req)

    def test_page_served(self):
        html = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/").read().decode()
        self.assertIn("Energy Audit", html)

    def test_calculate(self):
        data = json.load(self.post("/api/calculate", sample()))
        self.assertAlmostEqual(data["totals"]["cost_month"], 30000)

    def test_error_is_400(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post("/api/calculate", {"machines": []})
        self.assertEqual(cm.exception.code, 400)

    def test_csv_export(self):
        res = self.post("/api/export.csv", dict(sample(), org="Acme"))
        self.assertIn("text/csv", res.headers["Content-Type"])
        self.assertIn("Acme", res.read().decode())


if __name__ == "__main__":
    unittest.main()
