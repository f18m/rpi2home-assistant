# ha-alarm-raspy2mqtt

Small Python daemon to read normally-closed (NC) contacts from wired alarm sensors and publish them over MQTT for HomeAssistant.
This small utility also subscribes to MQTT to apply "switch" configurations to e.g. start/stop alarm sirens.

## Build system

This project uses `hatch` as build system (https://hatch.pypa.io/latest/).

## Permissions

This python code needs to run as `root` due to ensure access to the Raspberry I2C and GPIO peripherals.


## How to install on a Raspberry

This procedure has been tested on Raspbian 12 (bookworm):

```
sudo su
git clone https://github.com/f18m/ha-alarm-raspy2mqtt.git
cd ha-alarm-raspy2mqtt/
make raspbian_install
make raspbian_enable_at_boot
make raspbian_start
```

