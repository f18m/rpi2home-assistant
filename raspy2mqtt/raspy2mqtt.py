#!/usr/bin/python3

#
# This software is meant to run on a Raspberry PI having installed the 
# Sequent Microsystem 16 opto-insulated inputs HAT:
#  https://github.com/SequentMicrosystems/16inpind-rpi
# The script is meant to expose the 16 digital inputs read by Raspberry 
# over MQTT, to ease their integration as (binary) sensors in Home Assistant.
# This software is compatible with all 40-pin Raspberry Pi boards
# (Raspberry Pi 1 Model A+ & B+, Raspberry Pi 2, Raspberry Pi 3, Raspberry Pi 4,
# Raspberry Pi 5).
# The Sequent Microsystem board is connecting the pin 37 (GPIO 26) of the Raspberry Pi 
# to a pushbutton. This software monitors this pin, and if pressed for more than the
# desired time, issues the shut-down command.
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

# =======================================================================================================
# GLOBALs
# =======================================================================================================

THIS_SCRIPT_PYPI_PACKAGE = "ha-alarm-raspy2mqtt"

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
        self.inputs_map: Optional[Dict[int, Any]] = None
    
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
            self.inputs_map = {input_item['input_num']: input_item for input_item in self.config['inputs']}
            print(f"Loaded {len(self.inputs_map)} digital input configurations")
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

    @property
    def input_config(self, index: int) -> dict[str, any]:
        """
        Returns a dictionary exposing the fields:
            'name': name of the digital input
            'normally_closed': True or False
        """
        if self.inputs_map is None or index not in self.inputs_map:
            return {} # no meaningful default value
        return self.inputs_map[index]

# =======================================================================================================
# MAIN HELPERS
# =======================================================================================================

def parse_command_line():
    """Parses the command line and returns the configuration as dictionary object."""
    parser = argparse.ArgumentParser(
        description="Utility to expose the 16 digital inputs read by Raspberry over MQTT, to ease their integration as (binary) sensors in Home Assistant."
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


async def sample_values_and_publish_till_connected(cfg: CfgFile):
    """
    This function may throw a aiomqtt.MqttError exception indicating a connection issue!
    """
    global g_stats

    print(f"Connecting to MQTT broker at address {cfg.mqtt_broker}")
    g_stats["num_connections"] += 1
    loop = asyncio.get_running_loop()
    next_stat_time = loop.time() + 5.0
    async with aiomqtt.Client(cfg.mqtt_broker) as client:
        while True:
            # Read 16 digital inputs
            sampled_values_as_int = lib16inpind.readAll(0) # 0 means the first "stacked" board (this code supports only 1!)

            # Publish each input value as a separate MQTT topic
            for i in range(16):
                # Extract the bit at position i using bitwise AND operation
                bit_value = bool(sampled_values_as_int & (1 << i))

                input_cfg = cfg.inputs_map(i)
                if input_cfg is not None:
                    topic = f"home-assistant/{input_cfg.name}"

                    if input_cfg.normally_closed:
                        bit_value = not bit_value

                    if bit_value == True:
                        payload = '{"state":"ON"}'
                    else:
                        payload = '{"state":"OFF"}'

                    print(f"Publishing on mqtt topic {topic} the payload {payload}")
                    g_stats["num_samples"] += 1

                    # qos=1 means "at least once" QoS
                    await client.publish(topic, payload, qos=1)

            await asyncio.sleep(cfg.sampling_frequency_sec)
            if loop.time() >= next_stat_time:
                print_stats()
                next_stat_time = loop.time() + 5.0


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

    # wrap with error-handling code the main loop
    reconnection_interval_sec = 3
    while True:
        try:
            await sample_values_and_publish_till_connected(cfg)
        except aiomqtt.MqttError:
            print(f"Connection lost; reconnecting in {reconnection_interval_sec} seconds ...")
            await asyncio.sleep(reconnection_interval_sec)
        except KeyboardInterrupt:
            print_stats()
            print("Stopped by CTRL+C... aborting")
            return 0
    
    print_stats()
    return 0

# =======================================================================================================
# MAIN
# =======================================================================================================

if __name__ == "__main__":
    sys.exit(asyncio.run(main_loop()))
