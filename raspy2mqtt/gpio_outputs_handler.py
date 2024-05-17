#!/usr/bin/env python3

import gpiozero, asyncio, json, platform
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
        # global dictionary of gpiozero.LED instances used to drive outputs; key=MQTT topic
        self.output_channels = {}

        self.stats = {
            "num_connections_subscribe": 0,
            "num_mqtt_commands_processed": 0,
            "num_connections_publish": 0,
            "num_mqtt_states_published": 0,
            "num_connections_discovery_publish": 0,
            "num_mqtt_discovery_messages_published": 0,
            "ERR_invalid_payload_received": 0,
        }

    def init_hardware(self, cfg: AppConfig) -> None:
        if cfg.disable_hw:
            # populate with dummies the output channels:
            print("Skipping GPIO outputs HW initialization (--disable-hw was given)")
            for output_ch in cfg.get_all_outputs():
                topic_name = output_ch["mqtt"]["topic"]
                self.output_channels[topic_name] = DummyOutputCh(output_ch["gpio"])
        else:
            # setup GPIO pins for the OUTPUTs
            print(f"Initializing GPIO output pins")
            for output_ch in cfg.get_all_outputs():
                topic_name = output_ch["mqtt"]["topic"]
                active_high = not bool(output_ch["active_low"])
                self.output_channels[topic_name] = gpiozero.LED(pin=output_ch["gpio"], active_high=active_high)

    async def subscribe_and_activate_outputs(self, cfg: AppConfig):
        """
        Subscribes to MQTT topics that will receive commands to activate/turn-off GPIO outputs
        and takes care of interfacing with gpiozero to actually drive the GPIO output pin high or low.

        This function may throw an aiomqtt.MqttError exception indicating a connection issue!
        """
        print(
            f"Connecting to MQTT broker at address {cfg.mqtt_broker_host}:{cfg.mqtt_broker_port} to subscribe to OUTPUT commands"
        )
        self.stats["num_connections_subscribe"] += 1
        async with cfg.create_aiomqtt_client("_outputs_subscriber") as client:
            for output_ch in cfg.get_all_outputs():
                topic = output_ch["mqtt"]["topic"]
                print(f"GpioOutputsHandler: Subscribing to topic [{topic}]")
                await client.subscribe(topic)

            async for message in client.messages:
                # IMPORTANT: the message.payload and message.topic are not strings and would fail
                #            a direct comparison to strings... so convert them explicitly to strings first:
                mqtt_topic = str(message.topic)
                mqtt_payload = message.payload.decode("UTF-8")

                output_ch = cfg.get_output_config_by_mqtt_topic(mqtt_topic)
                assert (
                    output_ch is not None
                )  # this is garantueed because we subscribed only to topics that are present in config

                output_name = output_ch["name"]
                if mqtt_payload == output_ch["mqtt"]["payload_on"]:
                    print(
                        f"Received message for digital output [{output_name}] from topic [{mqtt_topic}] with payload {mqtt_payload}... changing GPIO output pin state"
                    )
                    self.output_channels[mqtt_topic].on()
                elif mqtt_payload == output_ch["mqtt"]["payload_off"]:
                    print(
                        f"Received message for digital output [{output_name}] from topic [{mqtt_topic}] with payload {mqtt_payload}... changing GPIO output pin state"
                    )
                    self.output_channels[mqtt_topic].off()
                else:
                    print(
                        f"Unrecognized payload received for digital output [{output_name}] from topic [{mqtt_topic}]: {mqtt_payload}"
                    )
                    self.stats["ERR_invalid_payload_received"] += 1

                self.stats["num_mqtt_commands_processed"] += 1

    async def publish_outputs_state(self, cfg: AppConfig):
        """
        For each output GPIO pin this function publishes over MQTT the 'state topic'.
        The 'state topic' is a HomeAssistant-thing that acts as confirmation of the output commands:
        only when the output truly can change from OFF->ON or from ON->OFF the state topic gets updated.

        This function may throw a aiomqtt.MqttError exception indicating a connection issue!
        """

        print(
            f"Connecting to MQTT broker at address {cfg.mqtt_broker_host}:{cfg.mqtt_broker_port} to publish OUTPUT states"
        )
        self.stats["num_connections_publish"] += 1
        output_status_map = {}
        async with cfg.create_aiomqtt_client("_outputs_state_publisher") as client:
            while not GpioOutputsHandler.stop_requested:
                for output_ch in cfg.get_all_outputs():
                    mqtt_topic = output_ch["mqtt"]["topic"]
                    mqtt_state_topic = output_ch["mqtt"]["state_topic"]
                    assert mqtt_topic in self.output_channels  # this should be garantueed due to initial setup
                    output_status = self.output_channels[mqtt_topic].is_lit

                    if mqtt_topic not in output_status_map or output_status_map[mqtt_topic] != output_status:
                        # need to publish an update over MQTT... the state has changed
                        mqtt_payload = (
                            output_ch["mqtt"]["payload_on"] if output_status else output_ch["mqtt"]["payload_off"]
                        )

                        # publish with RETAIN flag so that Home Assistant will always find an updated status on
                        # the broker about each switch
                        print(f"Publishing to topic {mqtt_state_topic} the payload {mqtt_payload}")
                        await client.publish(mqtt_state_topic, mqtt_payload, qos=MQTT_QOS_AT_LEAST_ONCE, retain=True)
                        self.stats["num_mqtt_states_published"] += 1

                        # remember the status we just published in order to later skip meaningless updates
                        # when there is no state change:
                        output_status_map[mqtt_topic] = output_status

                await asyncio.sleep(cfg.homeassistant_publish_period_sec)

    async def homeassistant_discovery_message_publish(self, cfg: AppConfig):
        """
        Publishes over MQTT a so-called 'discovery' message that allows HomeAssistant to automatically
        detect the binary_sensors associated with the GPIO inputs.
        See https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
        """
        print(
            f"Connecting to MQTT broker at address {cfg.mqtt_broker_host}:{cfg.mqtt_broker_port} to publish OUTPUT discovery messages"
        )
        self.stats["num_connections_discovery_publish"] += 1

        try:
            async with cfg.create_aiomqtt_client("_outputs_discovery_publisher") as client:
                while not GpioOutputsHandler.stop_requested:
                    print(f"Publishing DISCOVERY messages for GPIO OUTPUTs")
                    for entry in cfg.get_all_outputs():
                        mqtt_discovery_topic = f"{cfg.homeassistant_discovery_topic_prefix}/switch/{cfg.homeassistant_discovery_topic_node_id}/{entry['name']}/config"

                        # NOTE: the HomeAssistant unique_id is what appears in the config file as "name"
                        mqtt_payload_dict = {
                            "unique_id": entry["name"],
                            "name": entry["description"],
                            "command_topic": entry["mqtt"]["topic"],
                            "state_topic": entry["mqtt"]["state_topic"],
                            "payload_on": entry["mqtt"]["payload_on"],
                            "payload_off": entry["mqtt"]["payload_off"],
                            "device_class": entry["home_assistant"]["device_class"],
                            # "expire_after": entry['home_assistant']["expire_after"], -- not supported by MQTT switch :(
                            "device": {
                                "manufacturer": HOME_ASSISTANT_MANUFACTURER,
                                "model": THIS_SCRIPT_PYPI_PACKAGE,
                                "name": platform.node() + "-sensors",
                                "sw_version": cfg.app_version,
                                "identifiers": [THIS_SCRIPT_PYPI_PACKAGE + platform.node()],
                            },
                        }
                        if entry["home_assistant"]["icon"] is not None:
                            # add icon to the config of the entry:
                            mqtt_payload_dict["icon"] = entry["home_assistant"]["icon"]
                        mqtt_payload = json.dumps(mqtt_payload_dict)
                        await client.publish(mqtt_discovery_topic, mqtt_payload, qos=MQTT_QOS_AT_LEAST_ONCE)
                        self.stats["num_mqtt_discovery_messages_published"] += 1

                    await asyncio.sleep(cfg.homeassistant_discovery_message_period_sec)
        except Exception as e:
            print(f"EXCEPTION: {e}")

    def print_stats(self):
        print(f">> OUTPUTS:")
        print(
            f">>   Num (re)connections to the MQTT broker [subscribe channel]: {self.stats['num_connections_subscribe']}"
        )
        print(
            f">>   ERROR: invalid payloads received [subscribe channel]: {self.stats['ERR_invalid_payload_received']}"
        )
        print(
            f">>   Num commands for output channels processed from MQTT broker: {self.stats['num_mqtt_commands_processed']}"
        )
        print(f">>   Num (re)connections to the MQTT broker [publish channel]: {self.stats['num_connections_publish']}")
        print(
            f">>   Num states for output channels published on the MQTT broker: {self.stats['num_mqtt_states_published']}"
        )
        print(f"  >> OUTPUTs DISCOVERY messages:")
        print(
            f">>     Num (re)connections to the MQTT broker [subscribe channel]: {self.stats['num_connections_discovery_publish']}"
        )
        print(f">>     Num MQTT discovery messages published: {self.stats['num_mqtt_discovery_messages_published']}")
