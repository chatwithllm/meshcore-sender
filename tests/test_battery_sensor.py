"""Validate HA voltage metadata and unavailable handling without installing HA."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class Entity:
    available = True

    def __init__(self, coordinator, key, name):
        self.coordinator = coordinator
        self.key = key


class BatterySensorTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender/sensor.py"
        tree = ast.parse(path.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MeshCoreBatteryVoltage")
        namespace = {"MeshCoreEntity": Entity, "SensorEntity": object,
                     "SensorDeviceClass": SimpleNamespace(VOLTAGE="voltage"),
                     "SensorStateClass": SimpleNamespace(MEASUREMENT="measurement"),
                     "UnitOfElectricPotential": SimpleNamespace(VOLT="V")}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
        self.coordinator = SimpleNamespace(data={"health": {"battery": {
            "available": True, "voltage": 3.987, "sampled_at": 1234}}})
        self.sensor = namespace["MeshCoreBatteryVoltage"](self.coordinator)

    def test_voltage_supports_ha_history_not_percentage(self):
        self.assertEqual(self.sensor._attr_device_class, "voltage")
        self.assertEqual(self.sensor._attr_state_class, "measurement")
        self.assertEqual(self.sensor._attr_native_unit_of_measurement, "V")
        self.assertEqual(self.sensor.native_value, 3.987)
        self.assertTrue(self.sensor.available)
        self.assertEqual(self.sensor.key, "battery_voltage")

    def test_failure_does_not_publish_last_voltage_as_current(self):
        self.coordinator.data["health"]["battery"]["available"] = False
        self.assertIsNone(self.sensor.native_value)
        self.assertFalse(self.sensor.available)

    def test_legacy_server_without_battery_stays_unavailable(self):
        self.coordinator.data = {"health": {"radio_ok": True}}
        self.assertIsNone(self.sensor.native_value)
        self.assertFalse(self.sensor.available)
        self.coordinator.data = None
        self.assertFalse(self.sensor.available)


if __name__ == "__main__":
    unittest.main()
