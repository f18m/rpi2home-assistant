#!/usr/bin/env python3

import yaml, aiomqtt, datetime, os
from datetime import datetime, timezone
from raspy2mqtt.constants import *

from schema import Schema, And, Or, Use, Optional, SchemaError, Regex


#
# Author: fmontorsi
# Created: Apr 2024
# License: Apache license
#

# =======================================================================================================
# AppConfig
# =======================================================================================================


class AppConfig:
    """
    This class represents the configuration of this application.
    It contains helpers to read the YAML config file for this utility plus helpers to
    receive configurations from CLI options and from environment variables.

    This class is also in charge of filling all values that might be missing in the config file
    with their defaults. All default constants are stored in constants.py
    """

    def __init__(self):
        self.config: Optional[Dict[str, Any]] = None
        self.optoisolated_inputs_map: Optional[Dict[int, Any]] = None  # None means "not loaded at all"

        # config options related to CLI options:
        self.disable_hw = False  # can be get/set from the outside
        self.verbose = False

        # before launching MQTT connections, define a unique MQTT prefix identifier:
        self.mqtt_identifier_prefix = "haalarm_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        self.mqtt_schema_for_sensor_on_and_off = Schema(
            {
                Optional("topic"): str,
                Optional("payload_on"): str,
                Optional("payload_off"): str,
            }
        )
        self.mqtt_schema_for_edge_triggered_sensor = Schema(
            {
                Optional("topic"): str,
                "payload": str,  # for edge-triggered sensors it's hard to propose a meaningful default payload...
            }
        )
        self.home_assistant_schema = Schema(
            {
                "device_class": str,  # device_class is required because it's hard to guess...
                Optional("expire_after"): int,
            }
        )

        self.config_file_schema = Schema(
            {
                "mqtt_broker": {
                    "host": str,
                    Optional("reconnection_period_msec"): int,
                    Optional("publish_period_msec"): int,
                    Optional("user"): str,
                    Optional("password"): str,
                },
                Optional("log_stats_every"): int,
                Optional("i2c_optoisolated_inputs"): [
                    {
                        "name": Regex(r"^[a-z0-9_]+$"),
                        Optional("description"): str,
                        "input_num": int,
                        "active_low": bool,
                        Optional("mqtt"): self.mqtt_schema_for_sensor_on_and_off,
                        "home_assistant": self.home_assistant_schema,
                    }
                ],
                Optional("gpio_inputs"): [
                    {
                        "name": Regex(r"^[a-z0-9_]+$"),
                        Optional("description"): str,
                        "gpio": int,
                        "active_low": bool,
                        # mqtt is NOT optional for GPIO inputs... we need to have a meaningful payload to send
                        "mqtt": self.mqtt_schema_for_edge_triggered_sensor,
                        # home_assistant is not allowed for GPIO inputs, since they do not create binary_sensors
                    }
                ],
                Optional("outputs"): [
                    {
                        "name": Regex(r"^[a-z0-9_]+$"),
                        Optional("description"): str,
                        "gpio": int,
                        "active_low": bool,
                        Optional("mqtt"): self.mqtt_schema_for_sensor_on_and_off,
                        "home_assistant": self.home_assistant_schema,
                    }
                ],
            }
        )

    def check_gpio(self, idx: int):
        reserved_gpios = [
            SEQMICRO_INPUTHAT_SHUTDOWN_BUTTON_GPIO,
            SEQMICRO_INPUTHAT_INTERRUPT_GPIO,
            SEQMICRO_INPUTHAT_I2C_SDA,
            SEQMICRO_INPUTHAT_I2C_SCL,
        ]
        if idx < 1 or idx > 40:
            raise ValueError(
                f"Invalid GPIO index {idx}. The legal range is [1-40] since the Raspberry GPIO connector is a 40-pin connector."
            )
        # some GPIO pins are reserved and cannot be configured!
        if idx in reserved_gpios:
            raise ValueError(
                f"Invalid GPIO index {idx}: that GPIO pin is reserved for communication with the Sequent Microsystem HAT. Choose a different GPIO."
            )

    def populate_defaults_in_list_entry(
        self,
        entry_dict: dict,
        populate_mqtt: bool = True,
        populate_homeassistant: bool = True,
        has_payload_on_off: bool = True,
    ) -> dict:
        if "description" not in entry_dict:
            entry_dict["description"] = entry_dict["name"]

        if populate_mqtt:
            if "mqtt" not in entry_dict:
                entry_dict["mqtt"] = {}

            # an optional entry is the 'topic':
            if "topic" not in entry_dict["mqtt"]:
                entry_dict["mqtt"]["topic"] = f"{MQTT_TOPIC_PREFIX}/{entry_dict['name']}"
                print(f"Topic for {entry_dict['name']} defaults to [{entry_dict['mqtt']['topic']}]")

            if has_payload_on_off:
                if "payload_on" not in entry_dict["mqtt"]:
                    entry_dict["mqtt"]["payload_on"] = MQTT_DEFAULT_PAYLOAD_ON
                if "payload_off" not in entry_dict["mqtt"]:
                    entry_dict["mqtt"]["payload_off"] = MQTT_DEFAULT_PAYLOAD_OFF

        if populate_homeassistant:
            # the following assertion is justified because 'schema' library should garantuee
            # that we get here only if all entries in the config file do have the 'home_assistant' section
            assert "home_assistant" in entry_dict

            # the optional entry is the 'expire_after':
            if "expire_after" not in entry_dict["home_assistant"]:
                entry_dict["home_assistant"]["expire_after"] = HOME_ASSISTANT_DEFAULT_EXPIRE_AFTER_SEC
                print(f"Expire-after for {entry_dict['name']} defaults to [{HOME_ASSISTANT_DEFAULT_EXPIRE_AFTER_SEC}]")

        return entry_dict

    def load(self, cfg_yaml: str) -> bool:
        print(f"Loading configuration file {cfg_yaml}")
        try:
            with open(cfg_yaml, "r") as file:
                self.config = yaml.safe_load(file)
        except FileNotFoundError:
            print(f"Error: configuration file '{cfg_yaml}' not found.")
            return False
        except yaml.YAMLError as e:
            print(f"Error parsing YAML config file '{cfg_yaml}': {e}")
            return False

        try:
            self.config_file_schema.validate(self.config)
        except SchemaError as e:
            print("Failed YAML config file validation. Error follows.")
            print(e)
            return False

        try:
            # convert the 'i2c_optoisolated_inputs' part in a dictionary indexed by the DIGITAL INPUT CHANNEL NUMBER:
            self.optoisolated_inputs_map = {}

            if "i2c_optoisolated_inputs" not in self.config:
                # empty list: feature disabled
                self.config["i2c_optoisolated_inputs"] = []

            for input_item in self.config["i2c_optoisolated_inputs"]:
                idx = int(input_item["input_num"])
                if idx < 1 or idx > 16:
                    raise ValueError(
                        f"Invalid input_num {idx}. The legal range is [1-16] since the Sequent Microsystem HAT only handles 16 inputs."
                    )

                input_item = self.populate_defaults_in_list_entry(input_item)
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

        try:
            # convert the 'gpio_inputs' part in a dictionary indexed by the GPIO PIN NUMBER:
            self.gpio_inputs_map = {}

            if "gpio_inputs" not in self.config:
                # empty list: feature disabled
                self.config["gpio_inputs"] = []

            for input_item in self.config["gpio_inputs"]:
                idx = int(input_item["gpio"])
                self.check_gpio(idx)
                input_item = self.populate_defaults_in_list_entry(
                    input_item, populate_homeassistant=False, has_payload_on_off=False
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

            if "outputs" not in self.config:
                # empty list: feature disabled
                self.config["outputs"] = []

            for output_item in self.config["outputs"]:
                idx = int(output_item["gpio"])
                self.check_gpio(idx)
                output_item = self.populate_defaults_in_list_entry(output_item)
                self.outputs_map[output_item["mqtt"]["topic"]] = output_item
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

        print(f"Successfully loaded configuration")
        return True

    def merge_options_from_cli(self, args: dict):
        # merge CLI options into the configuration object:
        self.disable_hw = args.disable_hw
        self.verbose = args.verbose

    def merge_options_from_env_vars(self):
        # merge env vars into the configuration object:
        if os.environ.get("DISABLE_HW", None) != None:
            self.disable_hw = True
        if os.environ.get("VERBOSE", None) != None:
            self.verbose = True
        if os.environ.get("MQTT_BROKER_HOST", None) != None:
            # this particular env var can override the value coming from the config file:
            self.mqtt_broker_host = os.environ.get("MQTT_BROKER_HOST")
        if os.environ.get("MQTT_BROKER_PORT", None) != None:
            # this particular env var can override the value coming from the config file:
            self.mqtt_broker_port = os.environ.get("MQTT_BROKER_PORT")

    def print_config_summary(self):
        print("Config summary:")
        print("** MQTT")
        print(f"   MQTT broker host:port: {self.mqtt_broker_host}:{self.mqtt_broker_port}")
        if self.mqtt_broker_user != None:
            print(f"   MQTT broker authentication: ON")
        else:
            print(f"   MQTT broker authentication: OFF")
        print(f"   MQTT reconnection period: {self.mqtt_reconnection_period_sec}s")
        print(f"   MQTT publish period: {self.mqtt_publish_period_sec}s")
        print("** I2C isolated inputs:")
        if self.optoisolated_inputs_map is not None:
            for k, v in self.optoisolated_inputs_map.items():
                print(f"   input#{k}: {v['name']}")
        print("** GPIO inputs:")
        if self.gpio_inputs_map is not None:
            for k, v in self.gpio_inputs_map.items():
                print(f"   input#{k}: {v['name']}")
        print("** OUTPUTs:")
        i = 1
        if self.outputs_map is not None:
            for k, v in self.outputs_map.items():
                print(f"   output#{i}: {v['name']}")
            i += 1
        print("** MISC:")
        print(f"   Log stats every: {self.stats_log_period_sec}s")

    # MQTT

    @property
    def mqtt_broker_host(self) -> str:
        if self.config is None:
            return ""  # no meaningful default value
        return self.config["mqtt_broker"]["host"]

    @mqtt_broker_host.setter
    def mqtt_broker_host(self, value):
        self.config["mqtt_broker"]["host"] = value

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
            return MQTT_DEFAULT_BROKER_PORT  # the default MQTT broker port
        if "port" not in self.config["mqtt_broker"]:
            return MQTT_DEFAULT_BROKER_PORT  # the default MQTT broker port
        return self.config["mqtt_broker"]["port"]

    @mqtt_broker_port.setter
    def mqtt_broker_port(self, value):
        self.config["mqtt_broker"]["port"] = int(value)

    @property
    def mqtt_reconnection_period_sec(self) -> float:
        if self.config is None:
            return MQTT_DEFAULT_RECONNECTION_PERIOD_SEC  # the default reconnection interval

        try:
            # convert the user-defined timeout from msec to (floating) sec
            cfg_value = float(self.config["mqtt_broker"]["reconnection_period_msec"]) / 1000.0
            return cfg_value
        except:
            # in this case the key is completely missing or does contain an integer value
            return MQTT_DEFAULT_RECONNECTION_PERIOD_SEC  # default value

    @property
    def mqtt_publish_period_sec(self) -> float:
        if self.config is None:
            return MQTT_DEFAULT_PUBLISH_PERIOD_SEC  # default value
        try:
            cfg_value = float(self.config["mqtt_broker"]["publish_period_msec"]) / 1000.0
            return cfg_value
        except:
            # in this case the key is completely missing or does contain an integer value
            return MQTT_DEFAULT_PUBLISH_PERIOD_SEC  # default value

    def create_aiomqtt_client(self, identifier_str: str):
        return aiomqtt.Client(
            hostname=self.mqtt_broker_host,
            port=self.mqtt_broker_port,
            timeout=self.mqtt_reconnection_period_sec,
            username=self.mqtt_broker_user,
            password=self.mqtt_broker_password,
            identifier=self.mqtt_identifier_prefix + identifier_str,
        )

    @property
    def stats_log_period_sec(self) -> int:
        if self.config is None or "log_stats_every" not in self.config:
            return STATS_DEFAULT_LOG_PERIOD_SEC  # default value
        return int(self.config["log_stats_every"])

    #
    # OPTO-ISOLATED INPUTS
    #

    def get_optoisolated_input_config(self, index: int) -> dict[str, any]:
        """
        Returns a dictionary containing all the possible keys that are
        valid for an opto-isolated input config (see the SCHEMA in the load() API),
        including optional keys that were not given in the YAML.
        """
        if self.optoisolated_inputs_map is None or index not in self.optoisolated_inputs_map:
            return None  # no meaningful default value
        return self.optoisolated_inputs_map[index]

    #
    # GPIO INPUTS
    #

    def get_gpio_input_config(self, index: int) -> dict[str, any]:
        """
        Returns a dictionary containing all the possible keys that are
        valid for a GPIO input config (see the SCHEMA in the load() API),
        including optional keys that were not given in the YAML.
        """
        if self.gpio_inputs_map is None or index not in self.gpio_inputs_map:
            return None  # no meaningful default value
        return self.gpio_inputs_map[index]

    def get_all_gpio_inputs(self) -> list:
        """
        Returns a list of dictionaries with configurations
        """
        if "gpio_inputs" not in self.config:
            return None  # no meaningful default value
        return self.config["gpio_inputs"]

    #
    # OUTPUTS CONFIG
    #

    def get_output_config_by_mqtt_topic(self, topic: str) -> dict[str, any]:
        """
        Returns a dictionary containing all the possible keys that are
        valid for a GPIO output config (see the SCHEMA in the load() API),
        including optional keys that were not given in the YAML.
        """
        if self.outputs_map is None or topic not in self.outputs_map:
            return None  # no meaningful default value
        return self.outputs_map[topic]

    def get_all_outputs(self) -> list:
        """
        Returns a list of dictionaries with configurations
        """
        if "outputs" not in self.config:
            return None  # no meaningful default value
        return self.config["outputs"]
