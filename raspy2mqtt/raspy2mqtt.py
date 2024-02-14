#!/usr/bin/env python3

#
# This software is meant to run on a Raspberry PI having installed
# a) the Sequent Microsystem 16 opto-insulated inputs HAT:
#       https://github.com/SequentMicrosystems/16inpind-rpi
#    This software is meant to expose the 16 digital inputs from this HAT
#    over MQTT, to ease their integration as (binary) sensors in Home Assistant.
#    Note that Sequent Microsystem board is connecting the pin 37 (GPIO 26) of the Raspberry Pi 
#    to a pushbutton. This software monitors this pin, and if pressed for more than the
#    desired time, issues the shut-down command.
# b) a SeenGreat 2CH output opto-insulated relay HAT:
#       https://seengreat.com/wiki/107/
#    This software is meant to listen on MQTT topics and turn on/off the
#    two channels of this HAT.
#
# This software is compatible with all 40-pin Raspberry Pi boards
# (Raspberry Pi 1 Model A+ & B+, Raspberry Pi 2, Raspberry Pi 3, Raspberry Pi 4,
# Raspberry Pi 5).
#
# Author: fmontorsi
# Created: Feb 2024
# License: Apache license
#

import argparse
import os
import sys
import yaml
import asyncio
import aiomqtt
#import paho.mqtt as mqtt
import lib16inpind
from gpiozero import Button
import subprocess

# =======================================================================================================
# GLOBALs
# =======================================================================================================

THIS_SCRIPT_PYPI_PACKAGE = "ha-alarm-raspy2mqtt"
MQTT_TOPIC_PREFIX = "home-assistant"
MAX_INPUT_CHANNELS = 16
BROKER_CONNECTION_TIMEOUT_SEC = 3

# GPIO pin connected to the push button
SHUTDOWN_BUTTON_PIN = 26

g_stats = {
    'num_samples': 0,
    'num_connections': 0
}


# =======================================================================================================
# CfgFile
# =======================================================================================================

class CfgFile:
    """
    This class represents the YAML config file for this utility
    """

    def __init__(self):
        self.config: Optional[Dict[str, Any]] = None
        self.inputs_map: Optional[Dict[int, Any]] = None # None means "not loaded at all"
    
    def load(self, cfg_yaml: str) -> bool:
        try:
            with open(cfg_yaml, 'r') as file:
                self.config = yaml.safe_load(file)
            if not isinstance(self.config, dict):
                raise ValueError("Invalid YAML format: root element must be a dictionary")
            if 'mqtt' not in self.config:
                raise ValueError("Missing 'mqtt' section in the YAML config file")
            if 'broker' not in self.config['mqtt']:
                raise ValueError("Missing 'mqtt.broker' field in the YAML config file")
            if 'inputs' not in self.config:
                raise ValueError("Missing 'inputs' section in the YAML config file")
            if self.config['inputs'] is None:
                raise ValueError("Missing 'inputs' section in the YAML config file")
        except FileNotFoundError:
            print(f"Error: configuration file '{cfg_yaml}' not found.")
            return False
        except yaml.YAMLError as e:
            print(f"Error parsing YAML config file '{cfg_yaml}': {e}")
            return False
        except ValueError as e:
            print(f"Error in YAML config file '{cfg_yaml}': {e}")
            return False

        try:
            # convert the 'inputs' part in a dictionary indexed by the DIGITAL INPUT CHANNEL NUMBER:
            #self.inputs_map = {input_item['input_num']: input_item for input_item in self.config['inputs']}
            self.inputs_map = {}
            for input_item in self.config['inputs']:
                idx = input_item['input_num']
                self.inputs_map[idx] = input_item
                print(input_item)
            print(f"Loaded {len(self.inputs_map)} digital input configurations")
            if len(self.inputs_map)==0:
                # reset to "not loaded at all" condition
                self.inputs_map = None
        except ValueError as e:
            print(f"Error in YAML config file '{cfg_yaml}': {e}")
            return False
        except KeyError as e:
            print(f"Error in YAML config file '{cfg_yaml}': {e} is missing")
            return False

        return True

    @property
    def mqtt_broker(self) -> str:
        if self.config is None:
            return '' # no meaningful default value
        return self.config['mqtt']['broker']

    @property
    def sampling_frequency_sec(self) -> float:
        if self.config is None:
            return 1.0 # default value
        try:
            cfg_value = float(self.config['sampling_frequency_msec'])/1000.0
            return cfg_value
        except:
            # in this case the key is completely missing or does contain an integer value
            return 1.0 # default value

    def get_input_config(self, index: int) -> dict[str, any]:
        """
        Returns a dictionary exposing the fields:
            'name': name of the digital input
            'normally_closed': True or False
        """
        if self.inputs_map is None or index not in self.inputs_map:
            return {} # no meaningful default value
        return self.inputs_map[index]

    def get_output_config(self, index: int) -> dict[str, any]:
        """
        Returns a dictionary exposing the fields:
            'name': name of the digital input
            'gpio': integer identifying the GPIO pin using Raspy standard 40pin naming
        """
        if self.outputs_map is None or index not in self.outputs_map:
            return {} # no meaningful default value
        return self.outputs_map[index]

# =======================================================================================================
# MAIN HELPERS
# =======================================================================================================

def parse_command_line():
    """Parses the command line and returns the configuration as dictionary object."""
    parser = argparse.ArgumentParser(
        description=f"Utility to expose the {MAX_INPUT_CHANNELS} digital inputs read by Raspberry over MQTT, to ease their integration as (binary) sensors in Home Assistant."
    )

    # Optional arguments
    # NOTE: we cannot add required=True to --output option otherwise it's impossible to invoke this tool with just --version
    parser.add_argument(
        "-c",
        "--config",
        help="YAML file specifying the software configuration. Defaults to 'config.yaml'",
        default='config.yaml',
    )
    parser.add_argument(
        "-v", "--verbose", help="Be verbose.", action="store_true", default=False
    )
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

def print_stats():
    global g_stats
    print(f"Num samples published on the MQTT broker: {g_stats['num_samples']}")
    print(f"Num (re)connections to the MQTT broker: {g_stats['num_connections']}")

def shutdown():
    print(f"Triggering shutdown of the Raspberry PI")
    subprocess.call(['sudo', 'shutdown', '-h', 'now'])

# async def monitor_shutdown_button():
#     pressed_time = None
#     while True:
#         input_state = GPIO.input(SHUTDOWN_BUTTON_PIN)
        
#         # Button pressed
#         if input_state == GPIO.LOW:
#             # Start timer if not started
#             if pressed_time is None:
#                 pressed_time = asyncio.get_event_loop().time()
#             # Check if button pressed for more than 5 seconds
#             elif asyncio.get_event_loop().time() - pressed_time > 5:
#                 await shutdown()
#         # Button released
#         else:
#             pressed_time = None
        
#         # Add some delay to debounce
#         await asyncio.sleep(0.1)

async def sample_inputs_and_publish_till_connected(cfg: CfgFile):
    """
    This function may throw a aiomqtt.MqttError exception indicating a connection issue!
    """
    global g_stats

    print(f"Connecting to MQTT broker at address {cfg.mqtt_broker}")
    g_stats["num_connections"] += 1
    async with aiomqtt.Client(cfg.mqtt_broker, timeout=BROKER_CONNECTION_TIMEOUT_SEC) as client:
        while True:
            # Read 16 digital inputs
            sampled_values_as_int = lib16inpind.readAll(0) # 0 means the first "stacked" board (this code supports only 1!)

            # Publish each input value as a separate MQTT topic
            for i in range(MAX_INPUT_CHANNELS):
                # Extract the bit at position i using bitwise AND operation
                bit_value = bool(sampled_values_as_int & (1 << i))

                input_cfg = cfg.get_input_config(i)
                if input_cfg is not None:
                    # Choose the TOPIC and message PAYLOAD
                    topic = f"{MQTT_TOPIC_PREFIX}/{input_cfg['name']}"
                    if input_cfg['normally_closed']:
                        bit_value = not bit_value
                    if bit_value == True:
                        payload = '{"state":"ON"}'
                    else:
                        payload = '{"state":"OFF"}'

                    print(f"Publishing on mqtt topic {topic} the payload {payload}")
                    g_stats["num_samples"] += 1

                    # qos=1 means "at least once" QoS
                    await client.publish(topic, payload, qos=1)

            # Now sleep a little bit before repeating
            await asyncio.sleep(cfg.sampling_frequency_sec)

async def print_stats_periodically(cfg: CfgFile):
    loop = asyncio.get_running_loop()
    next_stat_time = loop.time() + 5.0        
    while True:
        # Print out stats to help debugging
        if loop.time() >= next_stat_time:
            print_stats()
            next_stat_time = loop.time() + 5.0
        
        await asyncio.sleep(1)

async def subscribe_and_activate_outputs_till_connected(cfg: CfgFile):
    """
    This function may throw a aiomqtt.MqttError exception indicating a connection issue!
    """
    global g_stats

    print(f"Connecting to MQTT broker at address {cfg.mqtt_broker}")
    async with aiomqtt.Client(cfg.mqtt_broker, timeout=BROKER_CONNECTION_TIMEOUT_SEC) as client:
        # TODO: for all OUTPUT channels run 1 subscribe
        await client.subscribe(f"{MQTT_TOPIC_PREFIX}/")

        # TODO: activatePIO pin
        async for message in client.messages:
            print(message.payload)


async def main_loop():
    args = parse_command_line()
    cfg = CfgFile()
    if not cfg.load(args.config):
        return 1 # invalid config file... abort with failure exit code
    
    # check if the opto-isolated input board from Sequent Microsystem is indeed present:
    try:
        _ = lib16inpind.readAll(0)
    except FileNotFoundError as e:
        print(f"Could not read from the Sequent Microsystem opto-isolated input board: {e}. Aborting.")
        return 2

    # setup GPIO connected to the pushbutton (input) and
    # assign the when_held function to be called when the button is held for more than 5 seconds
    # (NOTE: the way gpiozero works is that a new thread is spawned to listed for this event on the Raspy GPIO)
    button = Button(SHUTDOWN_BUTTON_PIN, hold_time=5)
    button.when_held = shutdown

    # setup GPIO for the outputs
    # TODO


    # wrap with error-handling code the main loop
    reconnection_interval_sec = 3
    keyb_interrupted = False
    while not keyb_interrupted:
        try:
            #await sample_inputs_and_publish_till_connected(cfg)

            # Use a task group to manage and await all tasks
            async with asyncio.TaskGroup() as tg:
                tg.create_task(sample_inputs_and_publish_till_connected(cfg))
                tg.create_task(print_stats_periodically(cfg))
                tg.create_task(subscribe_and_activate_outputs_till_connected(cfg))

        except* aiomqtt.MqttError as err:
            print(f"Connection lost: {err.exceptions}; reconnecting in {reconnection_interval_sec} seconds ...")
            await asyncio.sleep(reconnection_interval_sec)
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
    sys.exit(asyncio.run(main_loop()))
