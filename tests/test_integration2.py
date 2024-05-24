import pytest, os, time, signal
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.core.waiting_utils import wait_container_is_ready

# from testcontainers.core.utils import raise_for_deprecated_parameter
from paho.mqtt import client as mqtt_client
import paho.mqtt.enums
from queue import Queue
from typing import Optional

from tests.mosquitto_container import MosquittoContainer
from tests.raspy2mqtt_container import Raspy2MQTTContainer


@pytest.mark.integration
def test_mqtt_reconnection():

    broker = MosquittoContainer()
    broker.start()
    with Raspy2MQTTContainer(broker) as container:
        time.sleep(1)  # give time to the Raspy2MQTTContainer to fully start
        if not container.is_running():
            print(f"Container under test has stopped running while broker was still running?? test failed.")
            container.print_logs()
            assert False

        # BAM! stop the broker to simulate either a maintainance window or a power fault in the system where MQTT broker runs
        print("About to stop the broker...")
        broker.stop()
        time.sleep(0.5)
        if not container.is_running():
            print(f"Container under test has stopped running immediately after stopping the broker... test failed.")
            container.print_logs()
            assert False

        # NOTE: MQTT_DEFAULT_RECONNECTION_PERIOD_SEC is equal 1sec
        for idx in range(1, 3):
            time.sleep(1.5)
            if not container.is_running():
                print(
                    f"Container under test has stopped running probably after retrying the connection to the broker... test failed."
                )
                container.print_logs()
                assert False

        # ok seems the container is still up -- that's good -- now let's see if it can reconnect
        print("About to restart the broker...")
        try:
            broker.start()
        except Exception as e:
            print(e)
            assert False
        for idx in range(1, 3):
            time.sleep(1.5)
            if not container.is_running():
                print(
                    f"Container under test has stopped running probably after retrying the connection to the broker... test failed."
                )
                container.print_logs()
                assert False

        # now verify that there is also traffic on the topics:
        topics_under_test = ["home/opto_input_1"]
        broker.watch_topics(topics_under_test)
        time.sleep(4)
        msg_rate = broker.get_message_rate_in_watched_topic(topics_under_test[0])
        time.sleep(1000)
        assert msg_rate > 0

    broker.stop()
