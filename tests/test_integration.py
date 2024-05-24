import pytest, os, time, signal
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.core.waiting_utils import wait_container_is_ready

# from testcontainers.core.utils import raise_for_deprecated_parameter
from paho.mqtt import client as mqtt_client
import paho.mqtt.enums
from queue import Queue
from typing import Optional

# MosquittoContainer


class MosquittoContainer(DockerContainer):
    """
    Specialization of DockerContainer for MQTT broker Mosquitto.
    """

    TESTCONTAINER_CLIENT_ID = "TESTCONTAINER-CLIENT"
    DEFAULT_PORT = 1883
    CONFIG_FILE = "integration-test-mosquitto.conf"

    def __init__(
        self,
        image: str = "eclipse-mosquitto:latest",
        port: int = None,
        configfile: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs,
    ) -> None:
        # raise_for_deprecated_parameter(kwargs, "port_to_expose", "port")
        super().__init__(image, **kwargs)

        if port is None:
            self.port = MosquittoContainer.DEFAULT_PORT
        else:
            self.port = port
        self.password = password

        # setup container:
        self.with_exposed_ports(self.port)
        if configfile is None:
            # default config ifle
            TEST_DIR = os.path.dirname(os.path.abspath(__file__))
            configfile = os.path.join(TEST_DIR, MosquittoContainer.CONFIG_FILE)
        self.with_volume_mapping(configfile, "/mosquitto/config/mosquitto.conf")
        if self.password:
            # TODO: add authentication
            pass

        # helper used to turn asynchronous methods into synchronous:
        self.msg_queue = Queue()

        # dictionary of watched topics and their message counts:
        self.watched_topics = {}

        # reusable client context:
        self.client = None

    @wait_container_is_ready()
    def _connect(self) -> None:
        client, err = self.get_client()
        if err != paho.mqtt.enums.MQTTErrorCode.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Failed to estabilish a connection: {err}")

        interval = 1.0
        timeout = 5
        start = time.time()
        while True:
            duration = time.time() - start
            if client.is_connected():
                return
            if duration > timeout:
                raise TimeoutError(f"Failed to estabilish a connection after {timeout:.3f} " "seconds")
            # wait till secondary thread manages to connect successfully:
            time.sleep(interval)

    def get_client(self, **kwargs) -> tuple[mqtt_client.Client, paho.mqtt.enums.MQTTErrorCode]:
        """
        Get a paho.mqtt client connected to this container.
        Check the returned object is_connected() method before use

        Args:
            **kwargs: Keyword arguments passed to `paho.mqtt.client`.

        Returns:
            client: MQTT client to connect to the container.
            error: an error code or MQTT_ERR_SUCCESS.
        """
        err = paho.mqtt.enums.MQTTErrorCode.MQTT_ERR_SUCCESS
        if self.client is None:
            self.client = mqtt_client.Client(
                client_id=MosquittoContainer.TESTCONTAINER_CLIENT_ID,
                callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
                userdata=self,
                **kwargs,
            )

            # connect() is a blocking call:
            err = self.client.connect(self.get_container_host_ip(), int(self.get_exposed_port(self.port)))
            self.client.on_message = MosquittoContainer.on_message
            self.client.loop_start()  # launch a thread to call loop() and dequeue the message

        return self.client, err

    def start(self) -> "MosquittoContainer":
        super().start()
        self._connect()
        return self

    class WatchedTopicInfo:
        def __init__(self):
            self.count = 0
            self.timestamp_start_watch = time.time()
            self.last_payload = ""

        def on_message(self, msg: mqtt_client.MQTTMessage):
            self.count += 1
            # for simplicity: assume strings are used in integration tests and are UTF8-encoded:
            self.last_payload = msg.payload.decode("UTF-8")

        def get_count(self):
            return self.count

        def get_last_payload(self):
            return self.last_payload

        def get_rate(self):
            duration = time.time() - self.timestamp_start_watch
            if duration > 0:
                return self.count / duration
            return 0

    def on_message(client: mqtt_client.Client, mosquitto_container: "MosquittoContainer", msg: mqtt_client.MQTTMessage):
        # very verbose but useful for debug:
        # print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
        if msg.topic == "$SYS/broker/messages/received":
            mosquitto_container.msg_queue.put(msg)
        else:
            # this should be a topic added through the watch_topics() API...
            # just check it has not been removed (e.g. by unwatch_all):
            if msg.topic in mosquitto_container.watched_topics:
                mosquitto_container.watched_topics[msg.topic].on_message(msg)
            else:
                print(f"Received msg on topic [{msg.topic}] that is not being watched")

    def get_messages_received(self) -> int:
        """
        Returns the total number of messages received by the broker so far.
        """

        client, err = self.get_client()
        if not client.is_connected():
            raise RuntimeError(f"Could not connect to Mosquitto broker: {err}")

        client.subscribe("$SYS/broker/messages/received")

        # wait till we get the first message from the topic;
        # this wait will be up to 'sys_interval' second long (see mosquitto.conf)
        try:
            message = self.msg_queue.get(block=True, timeout=5)
            return int(message.payload.decode())
        except Queue.Empty:
            return 0

    def watch_topics(self, topics: list):
        client, err = self.get_client()
        if not client.is_connected():
            raise RuntimeError(f"Could not connect to Mosquitto broker: {err}")

        filtered_topics = []
        for t in topics:
            if t in self.watched_topics:
                continue  # nothing to do... the topic had already been subscribed
            self.watched_topics[t] = MosquittoContainer.WatchedTopicInfo()
            # the topic list is actually a list of tuples (topic_name,qos)
            filtered_topics.append((t, 0))

        # after subscribe() the on_message() callback will be invoked
        err, _ = client.subscribe(filtered_topics)
        if err != paho.mqtt.enums.MQTTErrorCode.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"Failed to subscribe to topics: {filtered_topics}")

    def unwatch_all(self):
        client, err = self.get_client()
        if not client.is_connected():
            raise RuntimeError(f"Could not connect to Mosquitto broker: {err}")

        # unsubscribe from all topics
        client.unsubscribe(list(self.watched_topics.keys()))
        self.watched_topics = {}

    def get_messages_received_in_watched_topic(self, topic: str) -> int:
        if topic not in self.watched_topics:
            raise RuntimeError(f"Topic {topic} is not watched! Fix the test")
        return self.watched_topics[topic].get_count()

    def get_last_payload_received_in_watched_topic(self, topic: str) -> int:
        if topic not in self.watched_topics:
            raise RuntimeError(f"Topic {topic} is not watched! Fix the test")
        return self.watched_topics[topic].get_last_payload()

    def get_message_rate_in_watched_topic(self, topic: str) -> int:
        if topic not in self.watched_topics:
            raise RuntimeError(f"Topic {topic} is not watched! Fix the test")
        return self.watched_topics[topic].get_rate()

    def publish_message(self, topic: str, payload: str):
        ret = self.client.publish(topic, payload)
        ret.wait_for_publish(timeout=2)
        if not ret.is_published():
            raise RuntimeError(f"Could not publish a message on topic {topic} to Mosquitto broker: {ret}")

    def print_logs(self) -> str:
        print("** BROKER LOGS [STDOUT]:")
        print(self.get_logs()[0].decode())
        print("** BROKER LOGS [STDERR]:")
        print(self.get_logs()[1].decode())


class Raspy2MQTTContainer(DockerContainer):
    """
    Specialization of DockerContainer to test this same repository artifact.
    """

    CONFIG_FILE = "integration-test-config.yaml"

    def __init__(self, broker: MosquittoContainer) -> None:
        super().__init__(image="ha-alarm-raspy2mqtt")

        TEST_DIR = os.path.dirname(os.path.abspath(__file__))
        cfgfile = os.path.join(TEST_DIR, Raspy2MQTTContainer.CONFIG_FILE)
        self.with_volume_mapping(cfgfile, "/etc/ha-alarm-raspy2mqtt.yaml", mode="ro")
        self.with_volume_mapping("/tmp", "/tmp", mode="rw")
        self.with_env("DISABLE_HW", "true")

        # IMPORTANT: to link with the MQTT broker we want to use the IP address internal to the docker network,
        #            and the standard MQTT port. The localhost:exposed_port address is not reachable from a
        #            docker container that has been started inside a docker network!
        broker_container = broker.get_wrapped_container()
        broker_ip = broker.get_docker_client().bridge_ip(broker_container.id)
        print(
            f"Linking the {self.image} container with the MQTT broker at host:ip {broker_ip}:{MosquittoContainer.DEFAULT_PORT}"
        )

        self.with_env("MQTT_BROKER_HOST", broker_ip)
        self.with_env("MQTT_BROKER_PORT", MosquittoContainer.DEFAULT_PORT)

    def is_running(self):
        self.get_wrapped_container().reload()  # force refresh of container status
        # status = self.get_wrapped_container().attrs["State"]['Status']
        status = self.get_wrapped_container().status  # same as above
        return status == "running"

    def print_logs(self) -> str:
        print("** Raspy2MQTTContainer LOGS [STDOUT]:")
        print(self.get_logs()[0].decode())
        print("** Raspy2MQTTContainer LOGS [STDERR]:")
        print(self.get_logs()[1].decode())


# GLOBALs

broker = MosquittoContainer()

# HELPERS


@pytest.fixture(scope="module", autouse=True)
def setup(request):
    """
    Fixture to setup and teardown the MQTT broker
    """
    broker.start()
    print("Broker successfully started")

    def remove_container():
        broker.stop()

    request.addfinalizer(remove_container)


# TESTS


@pytest.mark.integration
def test_mqtt_reconnection():

    with Raspy2MQTTContainer(broker=broker) as container:
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
        broker.start()
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
        assert msg_rate > 0


@pytest.mark.integration
def test_publish_for_optoisolated_inputs():

    topics_under_test = ["home/opto_input_1", "home/opto_input_2"]
    min_expected_msg = 10
    expected_msg_rate = 2  # in msgs/sec; see the 'publish_period_msec' inside Raspy2MQTTContainer.CONFIG_FILE

    with Raspy2MQTTContainer(broker=broker) as container:
        time.sleep(1)  # give time to the Raspy2MQTTContainer to fully start
        if not container.is_running():
            print(f"Container under test has stopped running... test failed.")
            container.print_logs()
            assert False

        broker.watch_topics(topics_under_test)  # start watching topic only after start to get accurate msg rate
        print(f"Waiting 6 seconds to measure msg rate in topics: {topics_under_test}")
        time.sleep(6)

        broker.print_logs()
        container.print_logs()

        print(f"Total messages received by the broker: {broker.get_messages_received()}")
        for t in topics_under_test:
            msg_count = broker.get_messages_received_in_watched_topic(t)
            msg_rate = broker.get_message_rate_in_watched_topic(t)
            print(f"** TEST RESULTS [{t}]")
            print(f"Total messages in topic [{t}]: {msg_count} msgs")
            print(f"Msg rate in topic [{t}]: {msg_rate} msgs/sec")

            def almost_equal(x, y, threshold=0.5):
                return abs(x - y) < threshold

            # checks
            assert msg_count >= min_expected_msg
            assert almost_equal(msg_rate, expected_msg_rate)

        broker.unwatch_all()


@pytest.mark.integration
def test_publish_for_gpio_inputs():

    topics_under_test = [
        {"topic_name": "gpio1", "expected_payload": "HEY"},
        {"topic_name": "gpio4", "expected_payload": "BYEBYE"},
    ]

    with Raspy2MQTTContainer(broker=broker) as container:
        time.sleep(1)  # give time to the Raspy2MQTTContainer to fully start
        if not container.is_running():
            print(f"Container under test has stopped running... test failed.")
            container.print_logs()
            assert False

        broker.watch_topics([t["topic_name"] for t in topics_under_test])

        container.get_wrapped_container().kill(signal.SIGUSR1)  # gpio #1 should trigger an MQTT message
        time.sleep(1)
        container.get_wrapped_container().kill(signal.SIGUSR1)  # gpio #2 should be skipped since it's unconfigured
        container.get_wrapped_container().kill(signal.SIGUSR1)  # gpio #3 should be skipped since it's unconfigured
        container.get_wrapped_container().kill(signal.SIGUSR1)  # gpio #4 should trigger an MQTT message
        time.sleep(1)

        container.print_logs()

        for t in topics_under_test:
            tname = t["topic_name"]
            msg_count = broker.get_messages_received_in_watched_topic(tname)
            last_payload = broker.get_last_payload_received_in_watched_topic(tname)
            print(f"** TEST RESULTS [{tname}]")
            print(f"Total messages in topic [{tname}]: {msg_count} msgs")
            print(f"Last payload in topic [{tname}]: {last_payload}")
            assert msg_count == 1
            assert last_payload == t["expected_payload"]

        broker.unwatch_all()


@pytest.mark.integration
def test_publish_subscribe_for_outputs():

    test_runs = [
        {"topic_name": "home/output_1", "payload": "ON", "expected_file_contents": "20: ON"},
        {"topic_name": "home/output_1", "payload": "OFF", "expected_file_contents": "20: OFF"},
        {"topic_name": "home/output_2", "payload": "OFF", "expected_file_contents": "21: OFF"},
        {"topic_name": "home/output_2", "payload": "ON", "expected_file_contents": "21: ON"},
    ]
    INTEGRATION_TESTS_OUTPUT_FILE = "/tmp/integration-tests-output"

    def get_associated_state_topic(topic_name: str):
        return topic_name + "/state"

    with Raspy2MQTTContainer(broker=broker) as container:
        time.sleep(1)  # give time to the Raspy2MQTTContainer to fully start
        if not container.is_running():
            print(f"Container under test has stopped running... test failed.")
            container.print_logs()
            assert False

        i = 0
        for t in test_runs:
            state_topic = get_associated_state_topic(t["topic_name"])
            broker.watch_topics([state_topic])

            # send on the broker a msg
            print(f"TEST#{i}: Asking the software to drive the output [{t['topic_name']}] to state [{t['payload']}]")
            broker.publish_message(t["topic_name"], t["payload"])

            # give time to the app to react to the published message:
            time.sleep(1)

            broker.print_logs()
            container.print_logs()

            # verify file gets written inside /tmp
            with open(INTEGRATION_TESTS_OUTPUT_FILE, "r") as opened_file:
                assert opened_file.read() == t["expected_file_contents"]

            # verify that the STATE TOPIC in the broker has been updated:
            msg_count = broker.get_messages_received_in_watched_topic(state_topic)
            last_payload = broker.get_last_payload_received_in_watched_topic(state_topic)
            assert (
                msg_count >= 1
            )  # the software should publish an initial message and then an update after it processes the request to change output state
            assert last_payload == t["payload"]
            broker.unwatch_all()

            i += 1
