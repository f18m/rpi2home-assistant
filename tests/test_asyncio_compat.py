import asyncio

import pytest

from raspy2mqtt.gpio_inputs_handler import GpioInputsHandler


class _FailingClient:
    async def __aenter__(self):
        raise asyncio.CancelledError()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConfig:
    mqtt_reconnection_period_sec = 0
    homeassistant_publish_period_sec = 0

    def create_aiomqtt_client(self, *args, **kwargs):
        return _FailingClient()


def test_gpio_inputs_handler_propagates_cancelled_error():
    handler = GpioInputsHandler()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(handler.process_gpio_inputs_queue_and_publish(_FakeConfig()))
