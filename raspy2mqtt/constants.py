#!/usr/bin/env python3

#
# Author: fmontorsi
# Created: Apr 2024
# License: Apache license
#


# MQTT constants
class MqttQOS:
    AT_LEAST_ONCE = 1


class MqttDefaults:
    PAYLOAD_ON = "ON"
    PAYLOAD_OFF = "OFF"
    BROKER_PORT = 1883
    RECONNECTION_PERIOD_SEC = 1


# HomeAssistant constants/defaults
class HomeAssistantDefaults:
    TOPIC_PREFIX = "rpi2home-assistant"
    DISCOVERY_TOPIC_PREFIX = "homeassistant"
    PUBLISH_PERIOD_SEC = 1
    DISCOVERY_PUBLISH_PERIOD_SEC = 100
    EXPIRE_AFTER_SEC = 30
    MANUFACTURER = "github.com/f18m"
    BUTTON_MOMENTARY_PRESS_SEC = 0.5
    ALLOWED_DEVICE_CLASSES = {
        # see https://www.home-assistant.io/integrations/binary_sensor/#device-class
        "binary_sensor": [
            "battery",
            "battery_charging",
            "carbon_monoxide",
            "cold",
            "connectivity",
            "door",
            "garage_door",
            "gas",
            "heat",
            "light",
            "lock",
            "moisture",
            "motion",
            "moving",
            "occupancy",
            "opening",
            "plug",
            "power",
            "presence",
            "problem",
            "running",
            "safety",
            "smoke",
            "sound",
            "tamper",
            "update",
            "vibration",
            "window",
        ],
        # see https://www.home-assistant.io/integrations/switch/#device-class
        "switch": ["outlet", "switch"],
        # see https://www.home-assistant.io/integrations/button/#device-class
        "button": ["identify", "restart", "update"],
    }


# SequentMicrosystem-specific constants
class SeqMicroHatConstants:
    STACK_LEVEL = 0  # 0 means the first "stacked" board (this code supports only 1!)
    MAX_CHANNELS = 16
    SHUTDOWN_BUTTON_GPIO = 26  # GPIO pin connected to the push button
    INTERRUPT_GPIO = 11  # GPIO pin connected to the interrupt line of the I/O expander (need pullup resistor)
    I2C_SDA = 2  # reserved for I2C communication between Raspberry CPU and the input HAT
    I2C_SCL = 3  # reserved for I2C communication between Raspberry CPU and the input HAT


# Generic app constants/defaults
class MiscAppDefaults:
    THIS_APP_NAME = "rpi2home-assistant"

    # File paths constants
    CONFIG_FILE = "/etc/rpi2home-assistant.yaml"
    INTEGRATION_TESTS_OUTPUT_FILE = "/tmp/integration-tests-output"

    # Misc constants
    STATS_LOG_PERIOD_SEC = 30
