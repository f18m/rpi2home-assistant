#!/usr/bin/env python3

#
# Author: fmontorsi
# Created: Apr 2024
# License: Apache license
#

THIS_SCRIPT_PYPI_PACKAGE = "ha-alarm-raspy2mqtt"
MQTT_TOPIC_PREFIX = "home"
MQTT_QOS_AT_LEAST_ONCE = 1

# SequentMicrosystem-specific constants
SEQMICRO_INPUTHAT_STACK_LEVEL = 0  # 0 means the first "stacked" board (this code supports only 1!)
SEQMICRO_INPUTHAT_MAX_CHANNELS = 16
SEQMICRO_INPUTHAT_SHUTDOWN_BUTTON_GPIO = 26  # GPIO pin connected to the push button
SEQMICRO_INPUTHAT_INTERRUPT_GPIO = (
    11  # GPIO pin connected to the interrupt line of the I/O expander (need pullup resistor)
)
SEQMICRO_INPUTHAT_I2C_SDA = 2  # reserved for I2C communication between Raspberry CPU and the input HAT
SEQMICRO_INPUTHAT_I2C_SCL = 3  # reserved for I2C communication between Raspberry CPU and the input HAT

# file paths
DEFAULT_CONFIG_FILE = "/etc/ha-alarm-raspy2mqtt.yaml"
INTEGRATION_TESTS_OUTPUT_FILE = "/tmp/integration-tests-output"