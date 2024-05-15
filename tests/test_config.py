import pytest
from raspy2mqtt.config import AppConfig


@pytest.mark.unit
def test_nonexisting_config_file_fails():
    x = AppConfig()
    assert x.load("a/path/that/does/not/exists") == False


@pytest.mark.unit
def test_empty_config_file_fails(tmpdir):
    # create config file to test:
    p = tmpdir.mkdir("cfg").join("testconfig.yaml")
    p.write("\n")

    x = AppConfig()
    assert x.load(str(p)) == False


MINIMAL_CFG = """
mqtt_broker:
  host: something
"""


@pytest.mark.unit
def test_minimal_config_file_succeeds(tmpdir):
    # create config file to test:
    p = tmpdir.mkdir("cfg").join("testconfig.yaml")
    p.write(MINIMAL_CFG)

    x = AppConfig()
    assert x.load(str(p)) == True
    assert x.mqtt_broker_host == "something"
    assert x.mqtt_broker_user is None
    assert x.get_optoisolated_input_config(1) is None
    assert len(x.get_all_gpio_inputs()) == 0
    assert len(x.get_all_outputs()) == 0


MINIMAL_CFG2 = """
mqtt_broker:
  host: something
i2c_optoisolated_inputs:
  - name: opto_input_1
    # no description, it's optional
    input_num: 1
    active_low: true
    # no mqtt, it's optional
    home_assistant:
      device_class: tamper
gpio_inputs:
  - name: radio_channel_a
    # no description, it's optional
    gpio: 27
    active_low: false
    mqtt:
      topic: alarmo/command
      payload: ARM_AWAY
outputs:
  - name: ext_alarm_siren
    # no description, it's optional
    gpio: 20
    active_low: true
    # no mqtt, it's optional
    home_assistant:
      device_class: switch
"""


@pytest.mark.unit
def test_minimal_config_file2_succeeds(tmpdir):
    # create config file to test:
    p = tmpdir.mkdir("cfg").join("testconfig.yaml")
    p.write(MINIMAL_CFG2)

    x = AppConfig()
    assert x.load(str(p)) == True
    assert x.mqtt_broker_host == "something"
    assert x.mqtt_broker_user is None

    # OPTO-ISOLATED INPUTS
    # check that all attributes have been populated with the defaults:
    assert x.get_optoisolated_input_config(1) == {
        "active_low": True,
        "description": "opto_input_1",
        "home_assistant": {"device_class": "tamper", "expire_after": 0},
        "input_num": 1,
        'mqtt': {'payload_off': 'OFF', 'payload_on': 'ON', 'topic': 'home/opto_input_1'},
        "name": "opto_input_1",
    }

    # GPIO INPUTS
    assert len(x.get_all_gpio_inputs()) == 1
    assert x.get_gpio_input_config(1) == None  # '1' is not a valid GPIO input
    assert x.get_gpio_input_config(27) == {
        "active_low": False,
        "description": "radio_channel_a",
        "gpio": 27,
        'mqtt': {'payload_off': 'OFF', 'payload_on': 'ON', 'payload': 'ARM_AWAY', 'topic': 'alarmo/command'},
        "name": "radio_channel_a",
    }

    # GPIO OUTPUTs
    assert len(x.get_all_outputs()) == 1
    assert x.get_output_config_by_mqtt_topic("non-existing") == None
    assert x.get_output_config_by_mqtt_topic("home/ext_alarm_siren") == {
        "active_low": True,
        "description": "ext_alarm_siren",
        "home_assistant": {"device_class": "switch", "expire_after": 0},
        "gpio": 20,
        'mqtt': {'payload_off': 'OFF', 'payload_on': 'ON', 'topic': 'home/ext_alarm_siren'},
        "name": "ext_alarm_siren",
    }




INVALID_INPUTNUM_CFG = """
mqtt_broker:
  host: something
i2c_optoisolated_inputs:
  - name: test
    input_num: 20  # but the board has only 16 channels
gpio_inputs: []
outputs: []
"""


@pytest.mark.unit
def test_wrong_config_file_fails(tmpdir):
    # create config file to test:
    p = tmpdir.mkdir("cfg").join("testconfig.yaml")
    p.write(INVALID_INPUTNUM_CFG)

    x = AppConfig()
    assert x.load(str(p)) == False
