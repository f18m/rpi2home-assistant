#!/usr/bin/env python3

#
# Author: fmontorsi
# Created: Apr 2024
# License: Apache license
#

# =======================================================================================================
# GLOBALs
# =======================================================================================================

# global stat dictionary
g_stats = {
    "optoisolated_inputs": {
        "num_readings": 0,
        "num_connections_publish": 0,
        "num_mqtt_messages": 0,
    },
    "gpio_inputs": {
        "num_connections_publish": 0,
        "num_gpio_notifications": 0,
        "num_mqtt_messages": 0,
        "ERROR_noconfig": 0,
    },
    "outputs": {
        "num_connections_subscribe": 0,
        "num_mqtt_commands_processed": 0,
        "num_connections_publish": 0,
        "num_mqtt_states_published": 0,
    },
    "num_connections_lost": 0,
}

def print_stats():
    global g_stats, g_start_time
    print_stats.counter = getattr(print_stats, "counter", 0) + 1
    print(f">> STAT REPORT #{print_stats.counter}")

    uptime_sec = time.time() - g_start_time
    m, s = divmod(uptime_sec, 60)
    h, m = divmod(m, 60)
    h = int(h)
    m = int(m)
    s = int(s)
    print(f">> Uptime: {h}:{m:02}:{s:02}")
    print(f">> Num times the MQTT broker connection was lost: {g_stats['num_connections_lost']}")

    x = g_stats["optoisolated_inputs"]
    print(f">> OPTO-ISOLATED INPUTS:")
    print(f">>   Num (re)connections to the MQTT broker [publish channel]: {x['num_connections_publish']}")
    print(f">>   Num MQTT messages published to the broker: {x['num_mqtt_messages']}")
    print(f">>   Num actual readings of optoisolated inputs: {x['num_readings']}")

    x = g_stats["gpio_inputs"]
    print(f">> GPIO INPUTS:")
    print(f">>   Num (re)connections to the MQTT broker [publish channel]: {x['num_connections_publish']}")
    print(f">>   Num GPIO activations detected: {x['num_gpio_notifications']}")
    print(f">>   Num MQTT messages published to the broker: {x['num_mqtt_messages']}")

    x = g_stats["outputs"]
    print(f">> OUTPUTS:")
    print(f">>   Num (re)connections to the MQTT broker [subscribe channel]: {x['num_connections_subscribe']}")
    print(f">>   Num commands for output channels processed from MQTT broker: {x['num_mqtt_commands_processed']}")
    print(f">>   Num (re)connections to the MQTT broker [publish channel]: {x['num_connections_publish']}")
    print(f">>   Num states for output channels published on the MQTT broker: {x['num_mqtt_states_published']}")

