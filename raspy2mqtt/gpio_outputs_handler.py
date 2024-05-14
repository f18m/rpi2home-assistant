#!/usr/bin/env python3

import gpiozero, time, asyncio, queue
from raspy2mqtt.constants import *
from raspy2mqtt.config import *

#
# Author: fmontorsi
# Created: May 2024
# License: Apache license
#

# =======================================================================================================
# DummyOutputCh
# =======================================================================================================


class DummyOutputCh:
    """
    This class exists just to make it easier to run integration tests on platforms that do not have
    true GPIO output pins (like a GitHub runner)
    """

    def __init__(self, gpio: int) -> None:
        self.is_lit = False
        self.gpio = gpio

    def on(self):
        print(
            f"INTEGRATION-TEST-HELPER: DummyOutputCh: ON method invoked... writing into {INTEGRATION_TESTS_OUTPUT_FILE}"
        )
        self.is_lit = True
        with open(INTEGRATION_TESTS_OUTPUT_FILE, "w") as opened_file:
            opened_file.write(f"{self.gpio}: ON")

    def off(self):
        print(
            f"INTEGRATION-TEST-HELPER: DummyOutputCh: OFF method invoked... writing into {INTEGRATION_TESTS_OUTPUT_FILE}"
        )
        self.is_lit = False
        with open(INTEGRATION_TESTS_OUTPUT_FILE, "w") as opened_file:
            opened_file.write(f"{self.gpio}: OFF")


# =======================================================================================================
# GpioOutputsHandler
# =======================================================================================================


class GpioOutputsHandler:
    """
    This class handles subscribing to MQTT topics and then based on what gets published it handles
    driving GPIO pins configured as outputs.
    It exposes a coroutine that can be 'await'ed, which handles subscriptions for commands and state publishing.
    """

    # the stop-request is not related to a particular instance of this class... it applies to any instance
    stop_requested = False

    def __init__(self):
        # global dictionary of gpiozero.LED instances used to drive outputs
        self.output_channels = {}

        self.stats = {
            "num_connections_subscribe": 0,
            "num_mqtt_commands_processed": 0,
            "num_connections_publish": 0,
            "num_mqtt_states_published": 0,
        }

    def init_hardware(self, cfg: AppConfig) -> None:

        if cfg.disable_hw:
            # populate with dummies the output channels:
            print("Skipping GPIO outputs HW initialization (--disable-hw was given)")
            for output_ch in cfg.get_all_outputs():
                output_name = output_ch["name"]
                self.output_channels[output_name] = DummyOutputCh(output_ch["gpio"])
        else:
            # setup GPIO pins for the OUTPUTs
            print(f"Initializing GPIO output pins")
            for output_ch in cfg.get_all_outputs():
                output_name = output_ch["name"]
                active_high = not bool(output_ch["active_low"])
                self.output_channels[output_name] = gpiozero.LED(pin=output_ch["gpio"], active_high=active_high)

    async def subscribe_and_activate_outputs(self, cfg: AppConfig):
        """
        This function may throw an aiomqtt.MqttError exception indicating a connection issue!
        """
        print(
            f"Connecting to MQTT broker at address {cfg.mqtt_broker_host}:{cfg.mqtt_broker_port} to subscribe to OUTPUT commands"
        )
        self.stats["outputs"]["num_connections_subscribe"] += 1
        async with cfg.create_aiomqtt_client("_outputs_subscriber") as client:
            for output_ch in cfg.get_all_outputs():
                topic = f"{MQTT_TOPIC_PREFIX}/{output_ch['name']}"
                print(f"Subscribing to topic {topic}")
                await client.subscribe(topic)

            async for message in client.messages:
                output_name = str(message.topic).removeprefix(f"{MQTT_TOPIC_PREFIX}/")
                c = cfg.get_output_config(output_name)
                print(
                    f"Received message for digital output [{output_name}] with payload {message.payload}... changing GPIO output pin state"
                )
                if message.payload == b"ON":
                    self.output_channels[output_name].on()
                else:
                    self.output_channels[output_name].off()
                self.stats["outputs"]["num_mqtt_commands_processed"] += 1

    async def publish_outputs_state(self, cfg: AppConfig):
        """
        This function may throw a aiomqtt.MqttError exception indicating a connection issue!
        """

        print(
            f"Connecting to MQTT broker at address {cfg.mqtt_broker_host}:{cfg.mqtt_broker_port} to publish OUTPUT states"
        )
        self.stats["outputs"]["num_connections_publish"] += 1
        output_status_map = {}
        async with cfg.create_aiomqtt_client("_outputs_state_publisher") as client:
            while not GpioOutputsHandler.stop_requested:
                for output_ch in cfg.get_all_outputs():
                    output_name = output_ch["name"]
                    assert output_name in self.output_channels  # this should be garantueed due to initial setup
                    output_status = self.output_channels[output_name].is_lit

                    if output_name not in output_status_map or output_status_map[output_name] != output_status:
                        # need to publish an update over MQTT... the state has changed
                        topic = f"{MQTT_TOPIC_PREFIX}/{output_name}/state"
                        payload = "ON" if output_status else "OFF"

                        # publish with RETAIN flag so that Home Assistant will always find an updated status on
                        # the broker about each switch
                        # print(f"Publishing to topic {topic} the payload {payload}")
                        await client.publish(topic, payload, qos=MQTT_QOS_AT_LEAST_ONCE, retain=True)
                        self.stats["outputs"]["num_mqtt_states_published"] += 1

                        # remember the status we just published in order to later skip meaningless updates
                        # when there is no state change:
                        output_status_map[output_name] = output_status

                await asyncio.sleep(cfg.mqtt_publish_period_sec)

    def print_stats(self):
        print(f">> OUTPUTS:")
        print(
            f">>   Num (re)connections to the MQTT broker [subscribe channel]: {self.stats['num_connections_subscribe']}"
        )
        print(
            f">>   Num commands for output channels processed from MQTT broker: {self.stats['num_mqtt_commands_processed']}"
        )
        print(f">>   Num (re)connections to the MQTT broker [publish channel]: {self.stats['num_connections_publish']}")
        print(
            f">>   Num states for output channels published on the MQTT broker: {self.stats['num_mqtt_states_published']}"
        )
