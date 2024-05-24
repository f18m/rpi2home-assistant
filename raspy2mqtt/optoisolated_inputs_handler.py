#!/usr/bin/env python3

import lib16inpind, time, asyncio, gpiozero, json, sys
from raspy2mqtt.constants import *
from raspy2mqtt.config import *

#
# Author: fmontorsi
# Created: May 2024
# License: Apache license
#

# =======================================================================================================
# OptoIsolatedInputsHandler
# =======================================================================================================


class OptoIsolatedInputsHandler:
    """
    This class handles sampling inputs from the
    [Sequent Microsystem 16 opto-insulated inputs HAT](https://sequentmicrosystems.com/collections/all-io-cards/products/16-universal-inputs-card-for-raspberry-pi)
    and publishing the results to MQTT.
    It exposes a coroutine that can be 'await'ed, which handles publishing.
    """

    # the stop-request is not related to a particular instance of this class... it applies to any instance
    stop_requested = False

    # the MQTT client identifier
    client_identifier = "_optoisolated_publisher"
    client_identifier_discovery_pub = "_optoisolated_discovery_publisher"

    def __init__(self):
        # last reading of the 16 digital opto-isolated inputs
        self.optoisolated_inputs_sampled_values = 0

        self.stats = {
            "num_readings": 0,
            "num_connections_publish": 0,
            "num_mqtt_messages": 0,
            "num_connections_discovery_publish": 0,
            "num_mqtt_discovery_messages_published": 0,
            "ERROR_num_connections_lost": 0,
        }

    def init_hardware(self, cfg: AppConfig) -> list[gpiozero.Button]:
        buttons = []
        if cfg.disable_hw:
            print("Skipping optoisolated inputs HW initialization (--disable-hw was given)")
        else:
            # check if the opto-isolated input board from Sequent Microsystem is indeed present:
            try:
                _ = lib16inpind.readAll(SEQMICRO_INPUTHAT_STACK_LEVEL)
            except FileNotFoundError as e:
                print(f"Could not read from the Sequent Microsystem opto-isolated input board: {e}. Aborting.")
                return 2
            except OSError as e:
                print(f"Error while reading from the Sequent Microsystem opto-isolated input board: {e}. Aborting.")
                return 2
            except BaseException as e:
                print(f"Error while reading from the Sequent Microsystem opto-isolated input board: {e}. Aborting.")
                return 2

            print(f"Initializing SequentMicrosystem GPIO interrupt line")
            b = gpiozero.Button(SEQMICRO_INPUTHAT_INTERRUPT_GPIO, pull_up=True)
            b.when_held = self.sample_optoisolated_inputs
            buttons.append(b)

            # do first sampling operation immediately:
            self.sample_optoisolated_inputs()

        return buttons

    def sample_optoisolated_inputs(self):
        """
        This function is invoked when the SequentMicrosystem hat triggers an interrupt saying
        "hey there is some change in my inputs"... so we read all the 16 digital inputs
        """

        # NOTE0: since this routine is invoked by the gpiozero library, it runs on a secondary OS thread
        #        so _in theory_ we should be using a mutex when writing to the global 'optoisolated_inputs_sampled_values'
        #        variable. In practice since it's a simple integer variable, I don't think the mutex is needed.
        # NOTE1: this is a blocking call that will block until the 16 inputs are sampled
        # NOTE2: this might raise a TimeoutError exception in case the I2C bus transaction fails
        self.optoisolated_inputs_sampled_values = lib16inpind.readAll(SEQMICRO_INPUTHAT_STACK_LEVEL)
        self.stats["num_readings"] += 1

        # FIXME: right now, it's hard to force-wake the coroutine
        # which handles publishing to MQTT
        # the reason is that we should be using
        #   https://docs.python.org/3/library/asyncio-sync.html#asyncio.Event
        # which is not thread-safe. And this function executes in GPIOzero secondary thread :(
        # This means that if an input changes rapidly from 0 to 1 and then back to 0, we might not
        # publish this to MQTT (depends on the MQTT publish frequency... nyquist frequency)

    async def publish_optoisolated_inputs(self, cfg: AppConfig):
        """
        Publishes over MQTT the status of all opto-isolated inputs.
        This function has a particularity: it's designed to continuously publish over MQTT the status of
        the input channels. This is a safety feature designed for alarm system: the subscriber can trigger
        an alarm if the stream of input sensors stops for some reason.
        """
        print(
            f"Connecting to MQTT broker with identifier {OptoIsolatedInputsHandler.client_identifier} to publish OPTOISOLATED INPUT states"
        )
        self.stats["num_connections_publish"] += 1
        while True:
            try:
                async with cfg.create_aiomqtt_client(OptoIsolatedInputsHandler.client_identifier) as client:
                    while not OptoIsolatedInputsHandler.stop_requested:
                        # Publish each sampled value as a separate MQTT topic
                        update_loop_start_sec = time.perf_counter()
                        for i in range(SEQMICRO_INPUTHAT_MAX_CHANNELS):

                            # IMPORTANT: this function expects something else to update the 'optoisolated_inputs_sampled_values'
                            #            integer, whenever it is necessary to update it

                            # Extract the bit at position i-th using bitwise AND operation
                            bit_value = bool(self.optoisolated_inputs_sampled_values & (1 << i))

                            # convert from zero-based index 'i' to 1-based index, as used in the config file
                            input_cfg = cfg.get_optoisolated_input_config(1 + i)
                            if input_cfg is not None:
                                if input_cfg["active_low"]:
                                    logical_value = not bit_value
                                    input_type = "active low"
                                else:
                                    logical_value = bit_value
                                    input_type = "active high"

                                payload = (
                                    input_cfg["mqtt"]["payload_on"]
                                    if logical_value
                                    else input_cfg["mqtt"]["payload_off"]
                                )
                                # print(f"From INPUT#{i+1} [{input_type}] read {int(bit_value)} -> {int(logical_value)}; publishing on mqtt topic [{topic}] the payload: {payload}")

                                await client.publish(input_cfg["mqtt"]["topic"], payload, qos=MQTT_QOS_AT_LEAST_ONCE)
                                self.stats["num_mqtt_messages"] += 1

                        update_loop_duration_sec = time.perf_counter() - update_loop_start_sec
                        # print(f"Updating all sensors on MQTT took {update_loop_duration_sec} secs")

                        # Now sleep a little bit before repeating
                        actual_sleep_time_sec = cfg.homeassistant_publish_period_sec
                        if actual_sleep_time_sec > update_loop_duration_sec:
                            # adjust for the time it took to update on MQTT broker all topics
                            actual_sleep_time_sec -= update_loop_duration_sec

                        await asyncio.sleep(actual_sleep_time_sec)
            except aiomqtt.MqttError as err:
                print(f"Connection lost: {err}; reconnecting in {cfg.mqtt_reconnection_period_sec} seconds ...")
                self.stats["ERROR_num_connections_lost"] += 1
                await asyncio.sleep(cfg.mqtt_reconnection_period_sec)
            except Exception as err:
                print(f"EXCEPTION: {err}")
                sys.exit(99)

    async def homeassistant_discovery_message_publish(self, cfg: AppConfig):
        """
        Publishes over MQTT a so-called 'discovery' message that allows HomeAssistant to automatically
        detect the binary_sensors associated with the GPIO inputs.
        See https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
        """
        print(
            f"Connecting to MQTT broker with identifier {OptoIsolatedInputsHandler.client_identifier_discovery_pub} to publish OPTOISOLATED INPUT discovery messages"
        )
        self.stats["num_connections_discovery_publish"] += 1

        while True:
            try:
                async with cfg.create_aiomqtt_client(
                    OptoIsolatedInputsHandler.client_identifier_discovery_pub
                ) as client:
                    while not OptoIsolatedInputsHandler.stop_requested:
                        print(f"Publishing DISCOVERY messages for OPTOISOLATED INPUTs")
                        for entry in cfg.get_all_optoisolated_inputs():
                            mqtt_discovery_topic = f"{cfg.homeassistant_discovery_topic_prefix}/binary_sensor/{cfg.homeassistant_discovery_topic_node_id}/{entry['name']}/config"

                            # NOTE: the HomeAssistant unique_id is what appears in the config file as "name"
                            mqtt_payload_dict = {
                                "unique_id": entry["name"],
                                "name": entry["description"],
                                "state_topic": entry["mqtt"]["topic"],
                                "payload_on": entry["mqtt"]["payload_on"],
                                "payload_off": entry["mqtt"]["payload_off"],
                                "device_class": entry["home_assistant"]["device_class"],
                                "expire_after": entry["home_assistant"]["expire_after"],
                                "device": cfg.get_device_dict(),
                            }
                            if entry["home_assistant"]["icon"] is not None:
                                # add icon to the config of the entry:
                                mqtt_payload_dict["icon"] = entry["home_assistant"]["icon"]
                            mqtt_payload = json.dumps(mqtt_payload_dict)
                            await client.publish(mqtt_discovery_topic, mqtt_payload, qos=MQTT_QOS_AT_LEAST_ONCE)
                            self.stats["num_mqtt_discovery_messages_published"] += 1

                        await asyncio.sleep(cfg.homeassistant_discovery_message_period_sec)
            except aiomqtt.MqttError as err:
                print(f"Connection lost: {err}; reconnecting in {cfg.mqtt_reconnection_period_sec} seconds ...")
                self.stats["ERROR_num_connections_lost"] += 1
                await asyncio.sleep(cfg.mqtt_reconnection_period_sec)
            except Exception as err:
                print(f"EXCEPTION: {err}")
                sys.exit(99)

    def print_stats(self):
        print(f">> OPTO-ISOLATED INPUTS:")
        print(f">>   Num (re)connections to the MQTT broker [publish channel]: {self.stats['num_connections_publish']}")
        print(f">>   Num MQTT messages published to the broker: {self.stats['num_mqtt_messages']}")
        print(f">>   Num actual readings of optoisolated inputs: {self.stats['num_readings']}")
        print(f">>   OPTO-ISOLATED DISCOVERY messages:")
        print(f">>     Num MQTT discovery messages published: {self.stats['num_mqtt_discovery_messages_published']}")
        print(f">>     Num (re)connections to the MQTT broker: {self.stats['num_connections_discovery_publish']}")
        print(f">>   ERROR: MQTT connections lost: {self.stats['ERROR_num_connections_lost']}")
