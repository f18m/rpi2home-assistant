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
            configfile = os.path.join(os.getcwd(), "integration-test-mosquitto.conf")
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

    def watch_topic(self, topic: str):
        if topic in self.watched_topics:
            return  # nothing to do... the topic had already been subscribed

        client, err = self.get_client()
        if not client.is_connected():
            raise RuntimeError(f"Could not connect to Mosquitto broker: {err}")

        self.watched_topics[topic] = MosquittoContainer.WatchedTopicInfo()

        # after subscribe() the on_message() callback will be invoked
        client.subscribe(topic)

    def get_messages_received_in_watched_topic(self, topic: str) -> int:
        if topic not in self.watched_topics:
            return 0
        return self.watched_topics[topic].get_count()

    def get_message_rate_in_watched_topic(self, topic: str) -> int:
        if topic not in self.watched_topics:
            return 0
        return self.watched_topics[topic].get_rate()


class Raspy2MQTTContainer(DockerContainer):
    """
    Specialization of DockerContainer to test this same repository artifact.
    """

    CONFIG_FILE = "integration-test-config.yaml"

    def __init__(self, broker: MosquittoContainer) -> None:
        super().__init__(image="ha-alarm-raspy2mqtt")

        cfgfile = os.path.join(os.getcwd(), Raspy2MQTTContainer.CONFIG_FILE)
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
def test_basic_publish():

    topic_under_test = "home/opto_input_1"
    min_expected_msg = 10
    expected_msg_rate = 2  # in msgs/sec; see the 'publish_period_msec' inside Raspy2MQTTContainer.CONFIG_FILE

    broker.watch_topic(topic_under_test)
    with Raspy2MQTTContainer(broker=broker) as container:
        msg_count = 0
        while msg_count < min_expected_msg:
            print(f"In watched topic [{topic_under_test}] counted {msg_count} messages so far...")
            time.sleep(1)
            msg_count = broker.get_messages_received_in_watched_topic(topic_under_test)

        msg_rate = broker.get_message_rate_in_watched_topic(topic_under_test)

        def almost_equal(x, y, threshold=0.5):
            return abs(x - y) < threshold

        assert almost_equal(msg_rate, expected_msg_rate)

        print("BROKER LOGS:")
        print(broker.get_logs()[0].decode())
        print("CONTAINER LOGS:")
        print(container.get_logs()[0].decode())
        print(f"Msg rate in topic [{topic_under_test}]: {msg_rate} msgs/sec")
        print(f"Total messages received by the broker: {broker.get_messages_received()}")
