#!/usr/bin/env python3

import lib16inpind, time, asyncio, gpiozero
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
    This class handles sampling inputs from the [Sequent Microsystem 16 opto-insulated inputs HAT](https://sequentmicrosystems.com/collections/all-io-cards/products/16-universal-inputs-card-for-raspberry-pi)
    and publishing the results to MQTT.
    It exposes a coroutine that can be 'await'ed, which handles publishing.
    """

    # the stop-request is not related to a particular instance of this class... it applies to any instance
    stop_requested = False

    payload_on = "ON"
    payload_off = "OFF"

    def __init__(self):
        # last reading of the 16 digital opto-isolated inputs
        self.optoisolated_inputs_sampled_values = 0

        self.stats = {
            "num_readings": 0,
            "num_connections_publish": 0,
            "num_mqtt_messages": 0,
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
        # This function is invoked when the SequentMicrosystem hat triggers an interrupt saying
        # "hey there is some change in my inputs"... so we read all the 16 digital inputs
        #
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
        This function may throw a aiomqtt.MqttError exception indicating a connection issue!
        """
        print(
            f"Connecting to MQTT broker at address {cfg.mqtt_broker_host}:{cfg.mqtt_broker_port} to publish OPTOISOLATED INPUT states"
        )
        self.stats["num_connections_publish"] += 1
        async with cfg.create_aiomqtt_client("_optoisolated_publisher") as client:
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
                        # Choose the TOPIC and message PAYLOAD
                        topic = f"{MQTT_TOPIC_PREFIX}/{input_cfg['name']}"
                        if input_cfg["active_low"]:
                            logical_value = not bit_value
                            input_type = "active low"
                        else:
                            logical_value = bit_value
                            input_type = "active high"

                        payload = (
                            OptoIsolatedInputsHandler.payload_on
                            if logical_value
                            else OptoIsolatedInputsHandler.payload_off
                        )
                        # print(f"From INPUT#{i+1} [{input_type}] read {int(bit_value)} -> {int(logical_value)}; publishing on mqtt topic [{topic}] the payload: {payload}")

                        await client.publish(topic, payload, qos=MQTT_QOS_AT_LEAST_ONCE)
                        self.stats["num_mqtt_messages"] += 1

                update_loop_duration_sec = time.perf_counter() - update_loop_start_sec
                # print(f"Updating all sensors on MQTT took {update_loop_duration_sec} secs")

                # Now sleep a little bit before repeating
                actual_sleep_time_sec = cfg.mqtt_publish_period_sec
                if actual_sleep_time_sec > update_loop_duration_sec:
                    # adjust for the time it took to update on MQTT broker all topics
                    actual_sleep_time_sec -= update_loop_duration_sec

                await asyncio.sleep(actual_sleep_time_sec)

    def print_stats(self):
        print(f">> OPTO-ISOLATED INPUTS:")
        print(f">>   Num (re)connections to the MQTT broker [publish channel]: {self.stats['num_connections_publish']}")
        print(f">>   Num MQTT messages published to the broker: {self.stats['num_mqtt_messages']}")
        print(f">>   Num actual readings of optoisolated inputs: {self.stats['num_readings']}")
