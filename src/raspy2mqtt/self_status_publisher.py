#!/usr/bin/env python3

#
# Author: fmontorsi
# Created: Mar 2026
# License: Apache license
#

import asyncio
import sys
import aiomqtt
from .constants import MqttQOS
from .config import AppConfig

# =======================================================================================================
# SelfStatusPublisher
# =======================================================================================================


class SelfStatusPublisher:
    """
    This class publishes the online/offline status of rpi2home-assistant itself on an MQTT status topic.
    When connected, it publishes a retained "online" message.
    It also sets up an LWT (Last Will and Testament) so the broker automatically publishes a retained
    "offline" message when the connection is lost.
    """

    # the stop-request is not related to a particular instance of this class... it applies to any instance
    stop_requested = False

    # the MQTT client identifier
    client_identifier = "_self_status"

    PAYLOAD_ONLINE = "online"
    PAYLOAD_OFFLINE = "offline"

    def __init__(self):
        self.stats = {
            "num_connections": 0,
            "ERROR_num_connections_lost": 0,
        }

    async def publish_status(self, cfg: AppConfig):
        """
        Connects to the MQTT broker with a LWT that will publish 'offline' (retained) on the status
        topic upon disconnection. Immediately after connecting, publishes 'online' (retained) on the
        same status topic. Keeps the connection alive until stop_requested is set.
        """
        status_topic = cfg.status_mqtt_topic
        will = aiomqtt.Will(
            topic=status_topic,
            payload=self.PAYLOAD_OFFLINE,
            qos=MqttQOS.AT_LEAST_ONCE,
            retain=True,
        )

        print(
            f"Connecting to MQTT broker with identifier {SelfStatusPublisher.client_identifier} to publish self status on topic [{status_topic}]"
        )
        self.stats["num_connections"] += 1
        while True:
            try:
                async with cfg.create_aiomqtt_client(SelfStatusPublisher.client_identifier, will=will) as client:
                    await client.publish(status_topic, self.PAYLOAD_ONLINE, qos=MqttQOS.AT_LEAST_ONCE, retain=True)
                    print(f"Published '{self.PAYLOAD_ONLINE}' to status topic [{status_topic}]")

                    # Keep connection alive so the LWT remains registered with the broker
                    while not SelfStatusPublisher.stop_requested:
                        await asyncio.sleep(1)

            except aiomqtt.MqttError as err:
                print(f"Connection lost: {err}; reconnecting in {cfg.mqtt_reconnection_period_sec} seconds ...")
                self.stats["ERROR_num_connections_lost"] += 1
                await asyncio.sleep(cfg.mqtt_reconnection_period_sec)
            except Exception as err:
                print(f"EXCEPTION: {err}")
                sys.exit(99)

    def print_stats(self):
        print(">> SELF STATUS PUBLISHER:")
        print(f">>   Num (re)connections to the MQTT broker: {self.stats['num_connections']}")
        print(f">>   ERROR: MQTT connections lost: {self.stats['ERROR_num_connections_lost']}")
