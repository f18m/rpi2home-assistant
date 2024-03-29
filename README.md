# ha-alarm-raspy2mqtt

Small Python daemon to transform a Raspberry into a bridge from GPIO pins and MQTT, for HomeAssistant usage.
In particular this software allows:
* sample a wide range of electrical signals (voltages), from 3V-48V AC or DC, using a dedicated Raspberry HAT
* sample 3.3V inputs from Raspberry GPIO pins
* use Raspberry GPIO pins in output mode to activate relays

All these features are implemented in an [Home Assistant](https://www.home-assistant.io/)-friendly fashion.
For example, this small utility also subscribes to MQTT to apply "switch" configurations to drive loads.

# Prerequisites

This software is meant to run on a Raspberry PI having installed
* the [Sequent Microsystem 16 opto-insulated inputs HAT](https://sequentmicrosystems.com/collections/all-io-cards/products/16-universal-inputs-card-for-raspberry-pi).
   This software is meant to expose the 16 digital inputs from this HAT
   over MQTT, to ease their integration as (binary) sensors in Home Assistant.
   Note that Sequent Microsystem board is connecting the pin 37 (GPIO 26) of the Raspberry Pi 
   to a pushbutton. This software monitors this pin, and if pressed for more than the
   desired time, issues the shut-down command.
* a [SeenGreat 2CH output opto-insulated relay HAT](https://seengreat.com/wiki/107/).
   This software is meant to listen on MQTT topics and turn on/off the
   two channels of this HAT.

This software is compatible with all 40-pin Raspberry Pi boards
(Raspberry Pi 1 Model A+ & B+, Raspberry Pi 2, Raspberry Pi 3, Raspberry Pi 4,
Raspberry Pi 5).

Another pre-requisite is that there is an MQTT broker running somewhere (e.g. a Mosquitto broker).

Final but important pre-requisite is Python >= 3.11, that for Raspberry means Debian bookworm 12 or Raspbian 12 or higher.


# Documentation

## Build system

This project uses `hatch` as build system (https://hatch.pypa.io/latest/).

## Permissions

This python code needs to run as `root` due to ensure access to the Raspberry I2C and GPIO peripherals.

## How to install on a Raspberry Pi with Debian Bookworm 12

Note that Raspbian with Python 3.11+ does not allow to install Python software using `pip`.
Trying to install a Python package that way leads to an error like:

```
error: externally-managed-environment [...]
```

That means that to install Python software, a virtual environment has to be used.
This procedure automates the creation of the venv and has been tested on Raspbian 12 (bookworm):

```
sudo su
# python3-dev is needed by a dependency (rpi-gpio) which compiles native C code
# pigpiod is a package providing the daemon that is required by the pigpio GPIO factory
apt install git python3-venv python3-dev pigpiod
cd /root
git clone https://github.com/f18m/ha-alarm-raspy2mqtt.git
cd ha-alarm-raspy2mqtt/
make raspbian_install
make raspbian_enable_at_boot
make raspbian_start
```

Then of course it's important to populate the configuration file, with the specific pinouts for your raspberry HATs
(see [Preqrequisites](#prerequisites) section). The file is located at `/etc/ha-alarm-raspy2mqtt.yaml`, see [config.yaml](config.yaml) for 
the documentation of the configuration options, with some basic example.


# Useful links

* [Sequent Microsystem 16 opto-insulated inputs python library](https://github.com/SequentMicrosystems/16inpind-rpi)
* [aiomqtt python library](https://github.com/sbtinstruments/aiomqtt)
* [AsyncIO tutorial](https://realpython.com/python-concurrency/#asyncio-version)
* [Home Assistant](https://www.home-assistant.io/)

Very similar project, more flexible and much bigger, targeting specific sensor boards:
* [mqtt-io](https://github.com/flyte/mqtt-io)

