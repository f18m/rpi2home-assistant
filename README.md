# ha-alarm-raspy2mqtt

Small Python daemon to read normally-closed (NC) contacts from wired alarm sensors and publish them over MQTT for HomeAssistant

## How to install on a Raspberry

This procedure has been tested on Raspbian 12 (bookworm):

```
python3 -m venv ha-alarm-raspy2mqtt-venv
source ha-alarm-raspy2mqtt-venv/bin/activate
git clone https://github.com/f18m/ha-alarm-raspy2mqtt.git
cd ha-alarm-raspy2mqtt
pip3 install .
```