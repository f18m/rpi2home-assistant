# rpi2home-assistant

This project provides a Python daemon to **transform a Raspberry into a bridge between GPIO inputs/outputs and HomeAssistant, through MQTT**.
In particular this software allows to:
* sample a wide range of electrical signals (voltages) from 3V-48V AC or DC, using a dedicated Raspberry HAT, and publish them on MQTT
* sample 3.3V inputs from Raspberry GPIO pins directly (with no isolation/protection/HAT), and publish them on MQTT
* listen to MQTT topics and use Raspberry GPIO pins in output mode to activate relays, using a dedicated Raspberry HAT / relay board or just use Raspberry GPIO pins in output mode directly to drive low-voltage electrical devices

All these features are implemented in an [Home Assistant](https://www.home-assistant.io/)-friendly fashion.
For example, this utility requires **no configuration on Home Assistant-side** thanks to MQTT discovery messages that are automatically published and let Home Assistant automatically discover the devices. In other words you will just need to prepare 1 configuration file (the _rpi2home-assistant_ config file) and that's it.

An example of a panel of sensors/actuators created using _rpi2home-assistant_ in Home Assistant 2024.5 (sensors names have been blurred for privacy reason; sensor/actuators status are shown in Italian language):

![Home Assistant screenshot](/docs/screenshot1.png?raw=true "Home Assistant screenshot")


# Prerequisites

This software is meant to run on a Raspberry PI.
In addition to standard GPIOs, _rpi2home-assistant_ **optionally** provides specific support for the following hat:

* [Sequent Microsystem 16 opto-insulated inputs HAT](https://sequentmicrosystems.com/collections/all-io-cards/products/16-universal-inputs-card-for-raspberry-pi). This hat allows to sample a wide range of electrical signals (voltages) from 3V-48V AC or DC. _rpi2home-assistant_ exposes the sampled values over MQTT, to ease their integration as (binary) sensors in Home Assistant.

<!--
Note that Sequent Microsystem board is connecting the pin 37 (GPIO 26) of the Raspberry Pi 
to a pushbutton. This software monitors this pin, and if pressed for more than the
desired time, issues the shut-down command to the Raspberry PI board.
-->

The suggested way to use a RaspberryPI to drive external loads is through the use of **relay boards**.
There are a number of alternatives available on the market. The majority of them is really simple and
ask for the 3.3V or 5V power supply and then connect to the RaspberryPI through GPIO pins either 
active high or active low.
A suggested hat exposing relays is:

* a [SeenGreat 2CH output opto-insulated relay HAT](https://seengreat.com/wiki/107/).
   This software is meant to listen on MQTT topics and turn on/off the
   two channels of this HAT.

Beyond that, this software is meant to be compatible with all 40-pin Raspberry Pi boards
(Raspberry Pi 1 Model A+ & B+, Raspberry Pi 2, Raspberry Pi 3, Raspberry Pi 4,
Raspberry Pi 5).

Software prerequisites are:
* you must have an **MQTT broker** running somewhere (e.g. a Mosquitto broker);
* **Python >= 3.11**; for Raspberry it means you must be using Debian bookworm 12 or [Raspberry Pi OS](https://www.raspberrypi.com/software/operating-systems/) 12 or higher;
* there is no particular constraint on the Home Assistant version, even if the project is continuously tested
  almost only against the latest Home Assistant version available.

# Documentation

## Build system

This project uses `poetry` as build system (https://python-poetry.org/) so the 'build' is as simple as:

```
python3 -m build
```

## Permissions

This python code needs to run as `root` due to ensure access to the Raspberry I2C and GPIO peripherals.

## How to install on a Raspberry Pi with Debian Bookworm 12

Note that [Raspberry Pi OS](https://www.raspberrypi.com/software/operating-systems/) with Python 3.11+ 
does not allow to install Python software using `pip`.
Trying to install a Python package that way leads to an error like:

```
error: externally-managed-environment [...]
```

That means that to install Python software, a virtual environment has to be used.
This procedure automates the creation of the venv and has been tested on Raspberry Pi OS 12 (bookworm):

```
sudo su
# python3-dev is needed by a dependency (rpi-gpio) which compiles native C code
# pigpiod is a package providing the daemon that is required by the pigpio GPIO factory
apt install git python3-venv python3-dev pigpiod
cd /root
git clone https://github.com/f18m/rpi2home-assistant.git
cd rpi2home-assistant/
make raspbian_install
make raspbian_enable_at_boot
make raspbian_start
```

Then of course it's important to populate the configuration file, with the specific pinouts for your raspberry HATs
(see [Preqrequisites](#prerequisites) section). 
The file is located at `/etc/rpi2home-assistant.yaml`, see [config.yaml](config.yaml) for 
the documentation of the configuration options, with some basic example.


## Check Application Outputs

After starting the application you can verify from the logs whether it's running successfully:

```
journalctl -u rpi2home-assistant --since="5min ago"
```

## How to test with Docker

This project also provides a multi-arch docker image to ease testing.
You can launch this software into a docker container by running:

```
docker run -d \
   --volume <your config file>:/etc/rpi2home-assistant.yaml \
   --privileged --hostname $(hostname) \
   ghcr.io/f18m/rpi2home-assistant:<latest version>
```


## Development

To develop changes you can create a branch and push changes there. Then:

```
make format
make lint
make docker
make test
```

To validate locally your changes.

Finally, once ready, check out your branch on your raspberry and then run:

```
python3 -m venv ~/rpi2home-assistant-venv
~/rpi2home-assistant-venv/bin/pip3 install .
source ~/rpi2home-assistant-venv/bin/activate
cd <checkout_folder>/raspy2mqtt
./raspy2mqtt -c /etc/rpi2home-assistant.yaml
```


# Useful links

* [Sequent Microsystem 16 opto-insulated inputs python library](https://github.com/SequentMicrosystems/16inpind-rpi)
* [aiomqtt python library](https://github.com/sbtinstruments/aiomqtt)
* [AsyncIO tutorial](https://realpython.com/python-concurrency/#asyncio-version)
* [Home Assistant](https://www.home-assistant.io/)

Very similar project, more flexible and much bigger, targeting specific sensor boards:
* [mqtt-io](https://github.com/flyte/mqtt-io)


# TODO

- Improve HomeAssistant DISCOVERY by publishing them only after HomeAssistant restarts
- Eventually get rid of GPIOZERO + PIGPIOD which consume CPU and also force use of e.g. the queue.Queue due to
  the multithreading issues
