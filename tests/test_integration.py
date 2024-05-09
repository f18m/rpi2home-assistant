import pytest, os, time
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from paho.mqtt import client as mqtt_client
from queue import Queue

# GLOBALS

broker = DockerContainer("eclipse-mosquitto").with_volume_mapping(os.path.join(os.getcwd(), "integration-test-mosquitto.conf"), "/mosquitto/config/mosquitto.conf").with_exposed_ports(1883)
pytest_client = "PYTEST-CLIENT"
msgQueue = Queue()

# HELPERS

@pytest.fixture(scope="module", autouse=True)
def setup(request):
    """
    Fixture to setup and teardown the MQTT broker
    """
    broker.start()

    def remove_container():
        broker.stop()

    request.addfinalizer(remove_container)

def get_message_count():
    client = mqtt_client.Client(client_id=pytest_client, callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2)
    client.connect("localhost", int(broker.get_exposed_port(1883)))
    def on_message(client, userdata, msg):
        print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
        msgQueue.put(msg)

    client.on_message = on_message
    client.subscribe("$SYS/broker/messages/received")
    message = msgQueue.get()
    return message

# TESTS

@pytest.mark.integration
def test_basic_publish():
    with DockerContainer("ha-alarm-raspy2mqtt").with_volume_mapping(os.path.join(os.getcwd(), "integration-test-config.yaml"), "/etc/ha-alarm-raspy2mqtt.yaml").with_env("DISABLE_HW", "true") as container:
        #time.sleep(1000)
        while get_message_count() < 10:
            print(get_message_count())
            print(broker.get_logs())
            print(container.get_logs())
    