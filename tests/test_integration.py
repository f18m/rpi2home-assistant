import pytest, os, time
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
            # self.with_command(f"redis-server --requirepass {self.password}")

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

        def increment_msg_count(self):
            self.count += 1

        def get_count(self):
            return self.count

        def get_rate(self):
            duration = time.time() - self.timestamp_start_watch
            if duration > 0:
                return self.count / duration
            return 0

    def on_message(client, mosquitto_container, msg):
        # very verbose but useful for debug:
        # print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
        if msg.topic == "$SYS/broker/messages/received":
            mosquitto_container.msg_queue.put(msg)
        else:
            mosquitto_container.watched_topics[msg.topic].increment_msg_count()

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

    def get_messages_received_in_watched_topic(self, topic: str) -> int:
        if topic not in self.watched_topics:
            return 0
        return self.watched_topics[topic].get_count()

    def get_message_rate_in_watched_topic(self, topic: str) -> int:
        if topic not in self.watched_topics:
            return 0
        return self.watched_topics[topic].get_rate()

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
        self.with_volume_mapping(cfgfile, "/etc/ha-alarm-raspy2mqtt.yaml")
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
def test_publish_optoisolated_inputs():

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
        time.sleep(600)

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
