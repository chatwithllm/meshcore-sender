"""Runtime PIN security boundary and encrypted API dispatch."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

spec=importlib.util.spec_from_file_location('runtime_pin',Path(__file__).resolve().parents[1]/'custom_components/meshcore_sender/bridge.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class PinTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service=SimpleNamespace(name='update_meshcore_pin')
        self.runtime=SimpleNamespace(available=True,services={1:self.service},client=SimpleNamespace(
            connected_address='bridge.local',execute_service=AsyncMock(return_value=SimpleNamespace(success=True))))
        self.entry=SimpleNamespace(data={'host':'bridge.local','noise_psk':'fixture-encryption'},runtime_data=self.runtime)
        self.hass=SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda _: [self.entry]))
        self.coordinator=SimpleNamespace(client=SimpleNamespace(host='bridge.local',range=SimpleNamespace(snapshot=lambda:{'running':False})))

    async def test_leading_zero_pin_is_not_returned_or_stored_in_ha(self):
        result=await module.update_radio_pin(self.hass,self.coordinator,'012345')
        self.runtime.client.execute_service.assert_awaited_once_with(self.service,{'password':'012345'},return_response=False)
        self.assertNotIn('012345',str(result))
        self.assertNotIn('password',self.entry.data)

    async def test_invalid_pins_do_not_reach_bridge(self):
        for pin in ('12345','1234567','abcdef','１２３４５６',123456):
            with self.assertRaises(ValueError): await module.update_radio_pin(self.hass,self.coordinator,pin)
        self.runtime.client.execute_service.assert_not_awaited()

    async def test_unencrypted_or_unrelated_bridge_is_rejected(self):
        self.entry.data.pop('noise_psk')
        with self.assertRaises(ValueError): await module.update_radio_pin(self.hass,self.coordinator,'012345')
        self.entry.data['noise_psk']='fixture'
        self.coordinator.client.host='other.local'
        with self.assertRaises(ValueError): await module.update_radio_pin(self.hass,self.coordinator,'012345')
        self.runtime.client.execute_service.assert_not_awaited()

    async def test_active_test_and_failed_save_are_rejected(self):
        self.coordinator.client.range.snapshot=lambda:{'running':True}
        with self.assertRaises(ValueError): await module.update_radio_pin(self.hass,self.coordinator,'012345')
        self.runtime.client.execute_service.assert_not_awaited()
        self.coordinator.client.range.snapshot=lambda:{'running':False}
        self.runtime.client.execute_service.return_value=SimpleNamespace(success=False)
        with self.assertRaises(ValueError): await module.update_radio_pin(self.hass,self.coordinator,'012345')
