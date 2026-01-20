# rpi2home-assistant

![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/f18m/rpi2home-assistant/main.yml)
![PyPI - Version](https://img.shields.io/pypi/v/rpi2home-assistant)

This project provides a Python daemon to **transform a [Raspberry PI](https://www.raspberrypi.com/) into a bridge between GPIO inputs/outputs and [Home Assistant](https://www.home-assistant.io/), through MQTT**.

In particular this software allows to:
* sample low-voltage inputs from Raspberry GPIO pins directly (with no isolation/protection/HAT), publish them on MQTT and get them exposed to Home Assistant as [binary sensors](https://www.home-assistant.io/integrations/binary_sensor.mqtt/);
* sample a wide range of electrical signals (voltages) from 3V-48V AC or DC, using a dedicated Raspberry HAT, publish them on MQTT and get them exposed to Home Assistant as [binary sensors](https://www.home-assistant.io/integrations/binary_sensor.mqtt/);
* expose Raspberry GPIO output pins in Home Assistant as [switches](https://www.home-assistant.io/integrations/switch.mqtt/) or as [buttons](https://www.home-assistant.io/integrations/button.mqtt/) to e.g. activate relays, using a dedicated Raspberry HAT / relay board or just drive low-voltage electrical devices;

All these features are implemented in an [Home Assistant](https://www.home-assistant.io/)-friendly fashion.
For example, this utility requires **no configuration on Home Assistant-side** thanks to [MQTT discovery messages](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) that are automatically published and let Home Assistant automatically discover the devices. In other words you will just need to prepare 1 configuration file (the _rpi2home-assistant_ config file) and that's it.
All properties of the exposed devices (names, icons, descriptions, etc) can be provided/customized in the _rpi2home-assistant_ config file.

An example of a panel of sensors/actuators created using _rpi2home-assistant_ in Home Assistant 2024.5 (sensor/switch/button names have been blurred for privacy reasons; binary sensor status is shown in Italian language):

![Home Assistant screenshot](/docs/screenshot1.png?raw=true "Home Assistant screenshot")


# Prerequisites

See [prerequisites.md](docs/prerequisites.md).

# Documentation

## Installation

See [install.md](docs/install.md).

## Configuration file

The configuration file of _rpi2home-assistant_ is of course `/etc/rpi2home-assistant.yaml`.
During the installation the default config file with dummy options is installed.
It is useful to showcase the syntax. See [config.yaml](config.yaml) for 
the full documentation of the configuration options.

## Permissions

This python code needs to run as `root` due to ensure access to the Raspberry I2C and GPIO peripherals.

## Logs

After starting the application you can verify from the logs whether it's running successfully:

```sh
journalctl -u rpi2home-assistant --since="5min ago"
```


# Development

See [development.md](docs/development.md).


# Useful links

* [Sequent Microsystem 16 opto-insulated inputs python library](https://github.com/SequentMicrosystems/16inpind-rpi)
* [aiomqtt python library](https://github.com/sbtinstruments/aiomqtt)
* [AsyncIO tutorial](https://realpython.com/python-concurrency/#asyncio-version)
* [Home Assistant](https://www.home-assistant.io/)

Very similar project, more flexible and much bigger, targeting specific sensor boards:
* [mqtt-io](https://github.com/flyte/mqtt-io)


# TODO

- Eventually get rid of GPIOZERO + PIGPIOD which consume CPU and also force use of e.g. the queue.Queue due to
  the multithreading issues; replace these 2 parts with direct Raspberry PI GPIO access?
