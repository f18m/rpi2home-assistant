#!/usr/bin/env python3

#
# Author: fmontorsi
# Created: Feb 2024
# License: Apache license
#
# TODO: add HomeAssistant discovery messages

import argparse
import os
import fcntl
import sys
import asyncio
import aiomqtt
import lib16inpind
import gpiozero
import subprocess
import time
import queue
from datetime import datetime, timezone
from stats import *
from config import *
from constants import *

# =======================================================================================================
# GLOBALs
# =======================================================================================================

# global dictionary of gpiozero.LED instances used to drive outputs
g_output_channels = {}

# thread-safe queue to communicate from GPIOzero secondary threads to main thread
g_gpio_queue = queue.Queue()

# global start time
g_start_time = time.time()

# last reading of the 16 digital opto-isolated inputs
g_optoisolated_inputs_sampled_values = 0

# global prefix for MQTT client identifiers
g_mqtt_identifier_prefix = ""


# =======================================================================================================
# MAIN HELPERS
# =======================================================================================================


def parse_command_line():
    """Parses the command line and returns the configuration as dictionary object."""
    parser = argparse.ArgumentParser(
        description=f"Utility to expose the {SEQMICRO_INPUTHAT_MAX_CHANNELS} digital inputs read by Raspberry over MQTT, to ease their integration as (binary) sensors in Home Assistant."
    )

    # Optional arguments
    # NOTE: we cannot add required=True to --output option otherwise it's impossible to invoke this tool with just --version
    parser.add_argument(
        "-c",
        "--config",
        help="YAML file specifying the software configuration. Defaults to 'config.yaml'",
        default="config.yaml",
    )
    parser.add_argument("-v", "--verbose", help="Be verbose.", action="store_true", default=False)
    parser.add_argument(
        "-V",
        "--version",
        help="Print version and exit",
        action="store_true",
        default=False,
    )

    if "COLUMNS" not in os.environ:
        os.environ["COLUMNS"] = "120"  # avoid too many line wraps
    args = parser.parse_args()

    global verbose
    verbose = args.verbose

    if args.version:
        try:
            from importlib.metadata import version
        except:
            from importlib_metadata import version
        this_script_version = version(THIS_SCRIPT_PYPI_PACKAGE)
        print(f"Version: {this_script_version}")
        sys.exit(0)

    return args


def instance_already_running(label="default"):
    """
    Detect if an an instance with the label is already running, globally
    at the operating system level.

    Using `os.open` ensures that the file pointer won't be closed
    by Python's garbage collector after the function's scope is exited.

    The lock will be released when the program exits, or could be
    released if the file pointer were closed.
    """

    lock_file_pointer = os.open(f"/tmp/instance_{label}.lock", os.O_WRONLY | os.O_CREAT)

    try:
        # LOCK_NB = lock non-blocking
        # LOCK_EX = exclusive lock
        fcntl.lockf(lock_file_pointer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        already_running = False
    except IOError:
        already_running = True

    return already_running


def create_aiomqtt_client(cfg: CfgFile, identifier_str: str):
    return aiomqtt.Client(
        hostname=cfg.mqtt_broker_host,
        port=cfg.mqtt_broker_port,
        timeout=cfg.mqtt_reconnection_period_sec,
        username=cfg.mqtt_broker_user,
        password=cfg.mqtt_broker_password,
        identifier=g_mqtt_identifier_prefix + identifier_str,
    )


# =======================================================================================================
# GPIOZERO helper functions
# These functions execute in the context of secondary threads created by gpiozero library
# and attached to INPUT button pressure
# =======================================================================================================


def shutdown():
    print(f"!! Detected long-press on the Sequent Microsystem button. Triggering clean shutdown of the Raspberry PI !!")
    subprocess.call(["sudo", "shutdown", "-h", "now"])


def sample_optoisolated_inputs():
    global g_stats, g_optoisolated_inputs_sampled_values

    # This function is invoked when the SequentMicrosystem hat triggers an interrupt saying
    # "hey there is some change in my inputs"... so we read all the 16 digital inputs
    #
    # NOTE0: since this routine is invoked by the gpiozero library, it runs on a secondary OS thread
    #        so _in theory_ we should be using a mutex when writing to the global 'g_optoisolated_inputs_sampled_values'
    #        variable. In practice since it's a simple integer variable, I don't think the mutex is needed.
    # NOTE1: this is a blocking call that will block until the 16 inputs are sampled
    # NOTE2: this might raise a TimeoutError exception in case the I2C bus transaction fails
    g_optoisolated_inputs_sampled_values = lib16inpind.readAll(SEQMICRO_INPUTHAT_STACK_LEVEL)
    g_stats["optoisolated_inputs"]["num_readings"] += 1


def publish_mqtt_message(device):
    print(f"!! Detected activation of GPIO{device.pin.number} !! ")
    g_gpio_queue.put(device.pin.number)


# =======================================================================================================
# ASYNC HELPERS
# =======================================================================================================


async def print_stats_periodically(cfg: CfgFile):
    loop = asyncio.get_running_loop()
    next_stat_time = loop.time() + cfg.stats_log_period_sec
    while True:
        # Print out stats to help debugging
        if loop.time() >= next_stat_time:
            print_stats()
            next_stat_time = loop.time() + cfg.stats_log_period_sec

        await asyncio.sleep(1)


async def publish_optoisolated_inputs(cfg: CfgFile):
    """
    This function may throw a aiomqtt.MqttError exception indicating a connection issue!
    """
    global g_stats, g_optoisolated_inputs_sampled_values, g_mqtt_identifier_prefix

    print(
        f"Connecting to MQTT broker at address {cfg.mqtt_broker_host}:{cfg.mqtt_broker_port} to publish OPTOISOLATED INPUT states"
    )
    g_stats["optoisolated_inputs"]["num_connections_publish"] += 1
    async with create_aiomqtt_client(cfg, "_optoisolated_publisher") as client:
        while True:
            # Publish each sampled value as a separate MQTT topic
            update_loop_start_sec = time.perf_counter()
            for i in range(SEQMICRO_INPUTHAT_MAX_CHANNELS):

                # IMPORTANT: this function expects something else to update the 'g_optoisolated_inputs_sampled_values'
                #            integer, whenever it is necessary to update it

                # Extract the bit at position i-th using bitwise AND operation
                bit_value = bool(g_optoisolated_inputs_sampled_values & (1 << i))

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

                    payload = "ON" if logical_value else "OFF"
                    # print(f"From INPUT#{i+1} [{input_type}] read {int(bit_value)} -> {int(logical_value)}; publishing on mqtt topic [{topic}] the payload: {payload}")

                    await client.publish(topic, payload, qos=MQTT_QOS_AT_LEAST_ONCE)
                    g_stats["optoisolated_inputs"]["num_mqtt_messages"] += 1

            update_loop_duration_sec = time.perf_counter() - update_loop_start_sec
            # print(f"Updating all sensors on MQTT took {update_loop_duration_sec} secs")

            # Now sleep a little bit before repeating
            await asyncio.sleep(cfg.mqtt_publish_period_sec - update_loop_duration_sec)


async def process_gpio_inputs_queue_and_publish(cfg: CfgFile):
    """
    This function may throw a aiomqtt.MqttError exception indicating a connection issue!
    """
    global g_stats, g_mqtt_identifier_prefix

    print(
        f"Connecting to MQTT broker at address {cfg.mqtt_broker_host}:{cfg.mqtt_broker_port} to publish GPIO INPUT states"
    )
    g_stats["gpio_inputs"]["num_connections_publish"] += 1
    async with create_aiomqtt_client(cfg, "_gpio_publisher") as client:
        while True:
            # get next notification coming from the gpiozero secondary thread:
            try:
                gpio_number = g_gpio_queue.get_nowait()
            except queue.Empty:
                # if there's no notification (typical case), then do not block the event loop
                # and keep processing other tasks... to ensure low-latency in processing the
                # GPIO inputs the sleep time is set equal to the MQTT publish freq
                await asyncio.sleep(cfg.mqtt_publish_period_sec)
                continue

            # there is a GPIO notification to process:
            gpio_config = cfg.get_gpio_input_config(gpio_number)
            g_stats["gpio_inputs"]["num_gpio_notifications"] += 1
            if gpio_config is None or "mqtt" not in gpio_config:
                print(
                    f"Main thread got notification of GPIO#{gpio_number} being activated but there is NO CONFIGURATION for that pin. Ignoring."
                )
                g_stats["gpio_inputs"]["ERROR_noconfig"] += 1
            else:
                # extract MQTT config
                mqtt_topic = gpio_config["mqtt"]["topic"]
                mqtt_command = gpio_config["mqtt"]["command"]
                mqtt_code = gpio_config["mqtt"]["code"]
                print(
                    f"Main thread got notification of GPIO#{gpio_number} being activated; a valid MQTT configuration is attached: topic={mqtt_topic}, command={mqtt_command}, code={mqtt_code}"
                )

                # now launch the MQTT publish
                # mqtt_payload = {
                #    "command": mqtt_command,
                #    "code": mqtt_code
                # }
                # mqtt_payload_str = json.dumps(mqtt_payload)
                mqtt_payload_str = mqtt_command
                await client.publish(mqtt_topic, mqtt_payload_str, qos=MQTT_QOS_AT_LEAST_ONCE)
                print(f"Sent on topic={mqtt_topic}, payload={mqtt_payload_str}")
                g_stats["gpio_inputs"]["num_mqtt_messages"] += 1

            g_gpio_queue.task_done()


async def subscribe_and_activate_outputs(cfg: CfgFile):
    """
    This function may throw an aiomqtt.MqttError exception indicating a connection issue!
    """
    global g_stats
    global g_output_channels, g_mqtt_identifier_prefix

    print(
        f"Connecting to MQTT broker at address {cfg.mqtt_broker_host}:{cfg.mqtt_broker_port} to subscribe to OUTPUT commands"
    )
    g_stats["outputs"]["num_connections_subscribe"] += 1
    async with create_aiomqtt_client(cfg, "_outputs_subscriber") as client:
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
                g_output_channels[output_name].on()
            else:
                g_output_channels[output_name].off()
            g_stats["outputs"]["num_mqtt_commands_processed"] += 1


async def publish_outputs_state(cfg: CfgFile):
    """
    This function may throw a aiomqtt.MqttError exception indicating a connection issue!
    """
    global g_stats, g_output_channels, g_mqtt_identifier_prefix

    print(
        f"Connecting to MQTT broker at address {cfg.mqtt_broker_host}:{cfg.mqtt_broker_port} to publish OUTPUT states"
    )
    g_stats["outputs"]["num_connections_publish"] += 1
    output_status_map = {}
    async with create_aiomqtt_client(cfg, "_outputs_state_publisher") as client:
        while True:
            for output_ch in cfg.get_all_outputs():
                output_name = output_ch["name"]
                output_status = g_output_channels[output_name].is_lit

                if output_name not in output_status_map or output_status_map[output_name] != output_status:
                    # need to publish an update over MQTT... the state has changed
                    topic = f"{MQTT_TOPIC_PREFIX}/{output_name}/state"
                    payload = "ON" if output_status else "OFF"

                    # publish with RETAIN flag so that Home Assistant will always find an updated status on
                    # the broker about each switch
                    # print(f"Publishing to topic {topic} the payload {payload}")
                    await client.publish(topic, payload, qos=MQTT_QOS_AT_LEAST_ONCE, retain=True)
                    g_stats["outputs"]["num_mqtt_states_published"] += 1

                    # remember the status we just published in order to later skip meaningless updates
                    # when there is no state change:
                    output_status_map[output_name] = output_status

            await asyncio.sleep(cfg.mqtt_publish_period_sec)


async def main_loop():
    global g_stats, g_mqtt_identifier_prefix

    args = parse_command_line()
    cfg = CfgFile()
    if not cfg.load(args.config):
        return 1  # invalid config file... abort with failure exit code

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

    # setup GPIO connected to the pushbutton (input) and
    # assign the when_held function to be called when the button is held for more than 5 seconds
    # (NOTE: the way gpiozero works is that a new thread is spawned to listed for this event on the Raspy GPIO)
    if "GPIOZERO_PIN_FACTORY" in os.environ:
        print(f"GPIO factory backend is: {os.environ['GPIOZERO_PIN_FACTORY']}")
    else:
        print(
            f"GPIO factory backend is the default one. This might fail on newer Raspbian versions with Linux kernel >= 6.6.20"
        )
    buttons = []
    print(f"Initializing SequentMicrosystem GPIO shutdown button")
    b = gpiozero.Button(SEQMICRO_INPUTHAT_SHUTDOWN_BUTTON_GPIO, hold_time=5)
    b.when_held = shutdown
    buttons.append(b)

    print(f"Initializing SequentMicrosystem GPIO interrupt line")
    b = gpiozero.Button(SEQMICRO_INPUTHAT_INTERRUPT_GPIO, pull_up=True)
    b.when_held = sample_optoisolated_inputs
    buttons.append(b)

    # setup GPIO pins for the INPUTs
    print(f"Initializing GPIO input pins")
    for input_ch in cfg.get_all_gpio_inputs():
        # the short hold-time is to ensure that the digital input is served ASAP (i.e. publish_mqtt_message gets
        # invoked almost immediately)
        active_high = not bool(input_ch["active_low"])
        b = gpiozero.Button(input_ch["gpio"], hold_time=0.1, pull_up=None, active_state=active_high)
        b.when_held = publish_mqtt_message
        buttons.append(b)

    # setup GPIO pins for the OUTPUTs
    print(f"Initializing GPIO output pins")
    global g_output_channels
    for output_ch in cfg.get_all_outputs():
        output_name = output_ch["name"]
        active_high = not bool(output_ch["active_low"])
        g_output_channels[output_name] = gpiozero.LED(pin=output_ch["gpio"], active_high=active_high)

    # before launching MQTT connections, define a unique MQTT prefix identifier:
    g_mqtt_identifier_prefix = "haalarm_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # wrap with error-handling code the main loop
    keyb_interrupted = False
    print(f"Starting main loop")
    while not keyb_interrupted:
        try:
            # Use a task group to manage and await all (endless) tasks
            async with asyncio.TaskGroup() as tg:
                tg.create_task(print_stats_periodically(cfg))
                # inputs:
                tg.create_task(publish_optoisolated_inputs(cfg))
                tg.create_task(process_gpio_inputs_queue_and_publish(cfg))
                # outputs:
                tg.create_task(subscribe_and_activate_outputs(cfg))
                tg.create_task(publish_outputs_state(cfg))

        except* aiomqtt.MqttError as err:
            print(f"Connection lost: {err.exceptions}; reconnecting in {cfg.mqtt_reconnection_period_sec} seconds ...")
            g_stats["num_connections_lost"] += 1
            await asyncio.sleep(cfg.mqtt_reconnection_period_sec)
        except* KeyboardInterrupt:
            print_stats()
            print("Stopped by CTRL+C... aborting")
            keyb_interrupted = True

    print_stats()
    return 0


# =======================================================================================================
# MAIN
# =======================================================================================================

if __name__ == "__main__":
    if instance_already_running("ha-alarm-raspy2mqtt"):
        print(
            f"Sorry, detected another instance of this daemon is already running. Using the same I2C bus from 2 sofware programs is not recommended. Aborting."
        )
        sys.exit(3)

    try:
        sys.exit(asyncio.run(main_loop()))
    except KeyboardInterrupt:
        print(f"Stopping due to CTRL+C")
