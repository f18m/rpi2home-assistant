import pytest
import time

from tests.mosquitto_container import MosquittoContainerEnhanced
from tests.raspy2mqtt_container import Raspy2MQTTContainer


@pytest.mark.integration
def test_mqtt_reconnection():

    broker = MosquittoContainerEnhanced()
    broker.start()
    with Raspy2MQTTContainer(broker) as container:
        time.sleep(1)  # give time to the Raspy2MQTTContainer to fully start
        if not container.is_running():
            print("Container under test has stopped running while broker was still running?? test failed.")
            container.print_logs()
            assert False

        for attempt in range(1, 3):
            # BAM! stop the broker to simulate either a maintainance window or a power fault in the system where MQTT broker runs
            print(f"Attempt {attempt}-th: Simulating BROKER failure stopping the broker container...")
            broker.stop()
            time.sleep(0.5)
            if not container.is_running():
                print("Container under test has stopped running immediately after stopping the broker... test failed.")
                container.print_logs()
                assert False

            # NOTE: MQTT_DEFAULT_RECONNECTION_PERIOD_SEC is equal 1sec
            for idx in range(1, 3):
                time.sleep(1.5)
                if not container.is_running():
                    print(
                        "Container under test has stopped running probably after retrying the connection to the broker... test failed."
                    )
                    container.print_logs()
                    assert False

            # ok seems the container is still up -- that's good -- now let's see if it can reconnect
            print(f"Attempt {attempt}-th: About to restart the broker...")
            try:
                broker.start()
            except Exception as e:
                print(e)
                assert False

            measure_period_sec = 5
            topics_under_test = ["rpi2home-assistant/opto_input_1"]
            broker.watch_topics(topics_under_test)
            print(f"Attempt {attempt}-th: Checking if messages are received from topics {topics_under_test} in the next {measure_period_sec}sec...")

            for idx in range(1, 3):
                time.sleep(1.5)
                if not container.is_running():
                    print(
                        "Container under test has stopped running probably after retrying the connection to the broker... test failed."
                    )
                    container.print_logs()
                    assert False

            # now verify that there is also traffic on the topics:
            time.sleep(measure_period_sec)
            msg_rate = broker.get_message_rate_in_watched_topic(topics_under_test[0])
            print(f"Attempt {attempt}-th: Measured message rate for topics {topics_under_test}: {msg_rate} msgs/sec")
            assert msg_rate > 0

        print("Test passed. Container logs should indicate several attempts to reconnect:")
        container.print_logs()

    broker.stop()
