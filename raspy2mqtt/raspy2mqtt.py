#!/usr/bin/python3

#
# This script is meant to run on a Raspberry PI having installed the 
# Sequent Microsystem 16 opto-insulated inputs HAT:
#  https://github.com/SequentMicrosystems/16inpind-rpi
# The script is meant to expose the 16 digital inputs read by Raspberry 
# over MQTT, to ease their integration as (binary) sensors in Home Assistant
#
# Author: fmontorsi
# Created: Feb 2024
# License: Apache license
#

import argparse
import os
import sys
import yaml
import asyncio_mqtt as aiomqtt
import paho.mqtt as mqtt

# =======================================================================================================
# GLOBALs
# =======================================================================================================

THIS_SCRIPT_PYPI_PACKAGE = "malloctag-tools"


# =======================================================================================================
# CfgFile
# =======================================================================================================

class CfgFile:
    """
    This class represents the YAML config file for this utility
    """

    def __init__(self):
        self.rules = []

    def load(self, cfg_yaml):
        wholeyaml = {}
        try:
            f = open(cfg_yaml, "r")
            text = f.read()
            f.close()
            wholeyaml = yaml.safe_load(text)
        except:
        #except json.decoder.JSONDecodeError as err:
            print(f"Invalid configuration YAML file '{cfg_yaml}': ")
            sys.exit(1)

        if "inputs" not in wholeyaml:
            print(f"Invalid configuration YAML file '{cfg_yaml}': missing  'inputs' main object")
            sys.exit(1)

        nrule = 0
        for input_dict in wholeyaml["inputs"]:
            if "input_num" not in input_dict:
                print(
                    f"WARN: In configuration YAML file '{cfg_yaml}': ignoring key missing the [input_num] property: '{input}'"
                )
                continue

        #print(
        #    f"Loaded {len()} input configurations from config file '{cfg_yaml}'."
        #)



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
        help="YAML file specifying the software configuration.",
        default=None,
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

async def main_loop():
    args = parse_command_line()
    c = CfgFile()
    c.load(args.config)

    async with aiomqtt.Client("test.mosquitto.org") as client:
        await client.publish("humidity/outside", payload=0.38)


# =======================================================================================================
# MAIN
# =======================================================================================================

if __name__ == "__main__":
    asyncio.run(main())
