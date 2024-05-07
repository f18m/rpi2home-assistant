#!/usr/bin/env python3

import yaml
from raspy2mqtt.constants import *

#
# Author: fmontorsi
# Created: Apr 2024
# License: Apache license
#

# =======================================================================================================
# CfgFile
# =======================================================================================================


class CfgFile:
    """
    This class represents the YAML config file for this utility
    """

    def __init__(self):
        self.config: Optional[Dict[str, Any]] = None
        self.optoisolated_inputs_map: Optional[Dict[int, Any]] = None  # None means "not loaded at all"

    def load(self, cfg_yaml: str) -> bool:
        print(f"Loading configuration file {cfg_yaml}")
        try:
            with open(cfg_yaml, "r") as file:
                self.config = yaml.safe_load(file)
            if not isinstance(self.config, dict):
                raise ValueError("Invalid YAML format: root element must be a dictionary")
            # check MQTT
            if "mqtt_broker" not in self.config or self.config["mqtt_broker"] is None:
                raise ValueError("Missing 'mqtt_broker' section in the YAML config file")
            if "host" not in self.config["mqtt_broker"]:
                raise ValueError("Missing 'mqtt_broker.host' field in the YAML config file")
            # check inputs
            if "i2c_optoisolated_inputs" not in self.config:
                raise ValueError("Missing 'i2c_optoisolated_inputs' section in the YAML config file")
            if self.config["i2c_optoisolated_inputs"] is None:
                raise ValueError("Missing 'i2c_optoisolated_inputs' section in the YAML config file")
            # check outputs
            if "outputs" not in self.config:
                raise ValueError("Missing 'outputs' section in the YAML config file")
            if self.config["outputs"] is None:
                raise ValueError("Missing 'outputs' section in the YAML config file")
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
            # convert the 'i2c_optoisolated_inputs' part in a dictionary indexed by the DIGITAL INPUT CHANNEL NUMBER:
            self.optoisolated_inputs_map = {}
            for input_item in self.config["i2c_optoisolated_inputs"]:
                idx = int(input_item["input_num"])
                if idx < 1 or idx > 16:
                    raise ValueError(
                        f"Invalid input_num {idx}. The legal range is [1-16] since the Sequent Microsystem HAT only handles 16 inputs."
                    )
                self.optoisolated_inputs_map[idx] = input_item
                # print(input_item)
            print(f"Loaded {len(self.optoisolated_inputs_map)} opto-isolated input configurations")
            if len(self.optoisolated_inputs_map) == 0:
                # reset to "not loaded at all" condition
                self.optoisolated_inputs_map = None
        except ValueError as e:
            print(f"Error in YAML config file '{cfg_yaml}': {e}")
            return False
        except KeyError as e:
            print(f"Error in YAML config file '{cfg_yaml}': {e} is missing")
            return False

        reserved_gpios = [
            SEQMICRO_INPUTHAT_SHUTDOWN_BUTTON_GPIO,
            SEQMICRO_INPUTHAT_INTERRUPT_GPIO,
            SEQMICRO_INPUTHAT_I2C_SDA,
            SEQMICRO_INPUTHAT_I2C_SCL,
        ]

        try:
            # convert the 'gpio_inputs' part in a dictionary indexed by the GPIO PIN NUMBER:
            self.gpio_inputs_map = {}
            for input_item in self.config["gpio_inputs"]:
                idx = int(input_item["gpio"])
                if idx < 1 or idx > 40:
                    raise ValueError(
                        f"Invalid input_num {idx}. The legal range is [1-40] since the Raspberry GPIO connector is a 40-pin connector."
                    )
                # some GPIO pins are reserved and cannot be configured!
                if idx in reserved_gpios:
                    raise ValueError(
                        f"Invalid input_num {idx}: that GPIO pin is reserved for communication with the Sequent Microsystem HAT. Choose a different GPIO."
                    )
                self.gpio_inputs_map[idx] = input_item
                # print(input_item)
            print(f"Loaded {len(self.gpio_inputs_map)} GPIO input configurations")
            if len(self.gpio_inputs_map) == 0:
                # reset to "not loaded at all" condition
                self.gpio_inputs_map = None
        except ValueError as e:
            print(f"Error in YAML config file '{cfg_yaml}': {e}")
            return False
        except KeyError as e:
            print(f"Error in YAML config file '{cfg_yaml}': {e} is missing")
            return False

        try:
            # convert the 'outputs' part in a dictionary indexed by the NAME:
            self.outputs_map = {}
            for output_item in self.config["outputs"]:
                self.outputs_map[output_item["name"]] = output_item
                # print(output_item)
            print(f"Loaded {len(self.outputs_map)} digital output configurations")
            if len(self.outputs_map) == 0:
                # reset to "not loaded at all" condition
                self.outputs_map = None
        except ValueError as e:
            print(f"Error in YAML config file '{cfg_yaml}': {e}")
            return False
        except KeyError as e:
            print(f"Error in YAML config file '{cfg_yaml}': {e} is missing")
            return False

        print(f"MQTT broker host:port: {self.mqtt_broker_host}:{self.mqtt_broker_port}")
        if self.mqtt_broker_user != None:
            print(f"MQTT broker authentication: ON")
        else:
            print(f"MQTT broker authentication: OFF")
        print(f"MQTT reconnection period: {self.mqtt_reconnection_period_sec}s")
        print(f"MQTT publish period: {self.mqtt_publish_period_sec}s")

        print(f"Successfully loaded configuration")

        return True

    @property
    def mqtt_broker_host(self) -> str:
        if self.config is None:
            return ""  # no meaningful default value
        return self.config["mqtt_broker"]["host"]

    @property
    def mqtt_broker_user(self) -> str:
        if self.config is None:
            return None  # default is unauthenticated
        if "user" not in self.config["mqtt_broker"]:
            return None  # default is unauthenticated
        return self.config["mqtt_broker"]["user"]

    @property
    def mqtt_broker_password(self) -> str:
        if self.config is None:
            return None  # default is unauthenticated
        if "password" not in self.config["mqtt_broker"]:
            return None  # default is unauthenticated
        return self.config["mqtt_broker"]["password"]

    @property
    def mqtt_broker_port(self) -> int:
        if self.config is None:
            return 1883  # the default MQTT broker port
        if "port" not in self.config["mqtt_broker"]:
            return 1883  # the default MQTT broker port
        return self.config["mqtt_broker"]["port"]

    @property
    def mqtt_reconnection_period_sec(self) -> float:
        if self.config is None:
            return 1.0  # the default reconnection interval

        try:
            # convert the user-defined timeout from msec to (floating) sec
            cfg_value = float(self.config["mqtt_broker"]["reconnection_period_msec"]) / 1000.0
            return cfg_value
        except:
            # in this case the key is completely missing or does contain an integer value
            return 1.0  # default value

    @property
    def mqtt_publish_period_sec(self) -> float:
        if self.config is None:
            return 1.0  # default value
        try:
            cfg_value = float(self.config["mqtt_broker"]["publish_period_msec"]) / 1000.0
            return cfg_value
        except:
            # in this case the key is completely missing or does contain an integer value
            return 1.0  # default value

    @property
    def stats_log_period_sec(self) -> int:
        if self.config is None or "log_stats_every" not in self.config:
            return 30  # default value
        return int(self.config["log_stats_every"])

    #
    # OPTO-ISOLATED INPUTS
    #

    def get_optoisolated_input_config(self, index: int) -> dict[str, any]:
        """
        Returns a dictionary exposing the fields:
            'name': name of the digital input
            'active_low': True or False
        Note: the indexes are 1-based
        """
        if self.optoisolated_inputs_map is None or index not in self.optoisolated_inputs_map:
            return None  # no meaningful default value
        return self.optoisolated_inputs_map[index]

    #
    # GPIO INPUTS
    #

    def get_all_gpio_inputs(self):
        """
        Returns a list of dictionaries exposing the fields:
             'name': name of the digital input
             'gpio': integer identifying the GPIO pin using Raspy standard 40pin naming
             'active_low': True or False
        """
        if "gpio_inputs" not in self.config:
            return None  # no meaningful default value
        return self.config["gpio_inputs"]

    def get_gpio_input_config(self, index: int) -> dict[str, any]:
        """
        Returns a dictionary exposing the fields:
            'name': name of the digital input
            'active_low': True or False
            'mqtt': a dictionary with more details about the TOPIC and PAYLOAD to send on input activation (see config.yaml)
        """
        if self.gpio_inputs_map is None or index not in self.gpio_inputs_map:
            return None  # no meaningful default value
        return self.gpio_inputs_map[index]

    #
    # OUTPUTS CONFIG
    #

    def get_output_config(self, name: str) -> dict[str, any]:
        """
        Returns a dictionary exposing the fields:
            'name': name of the digital output
            'gpio': integer identifying the GPIO pin using Raspy standard 40pin naming
            'active_low': True or False
        """
        if self.outputs_map is None or name not in self.outputs_map:
            return None  # no meaningful default value
        return self.outputs_map[name]

    def get_all_outputs(self):
        """
        Returns a list of dictionaries exposing the fields:
             'name': name of the digital output
             'gpio': integer identifying the GPIO pin using Raspy standard 40pin naming
             'active_low': True or False
        """
        if "outputs" not in self.config:
            return None  # no meaningful default value
        return self.config["outputs"]
