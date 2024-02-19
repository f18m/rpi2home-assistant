# ha-alarm-raspy2mqtt

Small Python daemon to read normally-closed (NC) contacts from wired alarm sensors and publish them over MQTT for HomeAssistant.
This small utility also subscribes to MQTT to apply "switch" configurations to e.g. start/stop alarm sirens.

This software is meant to run on a Raspberry PI having installed
* the [Sequent Microsystem 16 opto-insulated inputs HAT](https://github.com/SequentMicrosystems/16inpind-rpi)
   This software is meant to expose the 16 digital inputs from this HAT
   over MQTT, to ease their integration as (binary) sensors in Home Assistant.
   Note that Sequent Microsystem board is connecting the pin 37 (GPIO 26) of the Raspberry Pi 
   to a pushbutton. This software monitors this pin, and if pressed for more than the
   desired time, issues the shut-down command.
* a [SeenGreat 2CH output opto-insulated relay HAT](https://seengreat.com/wiki/107/)  
   This software is meant to listen on MQTT topics and turn on/off the
   two channels of this HAT.

This software is compatible with all 40-pin Raspberry Pi boards
(Raspberry Pi 1 Model A+ & B+, Raspberry Pi 2, Raspberry Pi 3, Raspberry Pi 4,
Raspberry Pi 5).


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

Then of course it's important to populate the configuration file, with the specific pinouts for your raspberry HATs
(see Overview). The file is located at `/etc/ha-alarm-raspy2mqtt.yaml`