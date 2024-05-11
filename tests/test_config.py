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
i2c_optoisolated_inputs: []
gpio_inputs: []
outputs: []
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
    input_num: 1
    active_low: true
gpio_inputs:
  - name: radio_channel_a
    gpio: 27
    active_low: false
    mqtt:
      topic: alarmo/command
      command: ARM_AWAY
      code: none
outputs:
  - name: ext_alarm_siren
    gpio: 20
    active_low: true
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
    assert x.get_optoisolated_input_config(1) == {"active_low": True, "input_num": 1, "name": "opto_input_1"}
    assert len(x.get_all_gpio_inputs()) == 1
    assert len(x.get_all_outputs()) == 1


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
