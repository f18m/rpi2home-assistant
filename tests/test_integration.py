import pytest, os, time
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.core.waiting_utils import wait_container_is_ready
#from testcontainers.core.utils import raise_for_deprecated_parameter
from paho.mqtt import client as mqtt_client
import paho.mqtt.enums
from queue import Queue
from typing import Optional

# MosquittoContainer

testcontainer_client_id = "TESTCONTAINER-CLIENT"

class MosquittoContainer(DockerContainer):
    """
    Specialization of DockerContainer for MQTT broker Mosquitto.
    """

    def __init__(self, image: str = "eclipse-mosquitto:latest", port: int = 1883, configfile: Optional[str] = None, password: Optional[str] = None, **kwargs) -> None:
        #raise_for_deprecated_parameter(kwargs, "port_to_expose", "port")
        super().__init__(image, **kwargs)
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
            #self.with_command(f"redis-server --requirepass {self.password}")

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
                    client_id=testcontainer_client_id, 
                    callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
                    userdata=self,
                    **kwargs)
        
            # connect() is a blocking call:
            err = self.client.connect(self.get_container_host_ip(), int(self.get_exposed_port(self.port)))
            self.client.on_message = MosquittoContainer.on_message
            self.client.loop_start() # launch a thread to call loop() and dequeue the message
        
        return self.client, err

    def start(self) -> "MosquittoContainer":
        super().start()
        self._connect()
        return self

    def on_message(client, mosquitto_container, msg):
        print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
        if msg.topic == "$SYS/broker/messages/received":
            mosquitto_container.msg_queue.put(msg)
        else:
            mosquitto_container.watched_topics[msg.topic] += 1

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
            return # nothing to do... the topic had already been subscribed

        client, err = self.get_client()
        if not client.is_connected():
            raise RuntimeError(f"Could not connect to Mosquitto broker: {err}")

        self.watched_topics[topic] = 0

        # after subscribe() the on_message() callback will be invoked
        client.subscribe(topic)
        
    def get_messages_received_in_watched_topic(self, topic: str) -> int:
        if topic not in self.watched_topics:
            return 0
        return self.watched_topics[topic]


# GLOBALs

broker = MosquittoContainer()

# HELPERS

@pytest.fixture(scope="module", autouse=True)
def setup(request):
    """
    Fixture to setup and teardown the MQTT broker
    """
    broker.start()
    print("started")

    def remove_container():
        broker.stop()

    request.addfinalizer(remove_container)

# TESTS

@pytest.mark.integration
def test_basic_publish():

    topic_under_test = "home/opto_input_1"
    broker.watch_topic(topic_under_test)

    with DockerContainer("ha-alarm-raspy2mqtt").with_volume_mapping(os.path.join(os.getcwd(), "integration-test-config.yaml"), "/etc/ha-alarm-raspy2mqtt.yaml").with_env("DISABLE_HW", "true") as container:
        #time.sleep(1000)
        msg_count = broker.get_messages_received_in_watched_topic(topic_under_test)
        while msg_count < 10:
            print(msg_count)
            time.sleep(1)
            msg_count = broker.get_messages_received_in_watched_topic(topic_under_test)
        print(broker.get_logs()[0].decode())
        print(container.get_logs()[0].decode())
        print(broker.get_messages_received())
    