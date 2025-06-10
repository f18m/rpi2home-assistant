# Prerequisites

This software is meant to run on a Raspberry PI. Any other target platform is currently not supported.
This section provides more information about _hardware_ and _software_ prerequisites on the Raspberry PI.

## Supported Raspberry PI variants

This software is meant to be compatible with all 40-pin Raspberry Pi boards
(Raspberry Pi 1 Model A+ & B+, Raspberry Pi 2, Raspberry Pi 3, Raspberry Pi 4,
Raspberry Pi 5).

## Supported Hardware

In addition to standard GPIOs, _rpi2home-assistant_ **optionally** provides specific support for the following hat:

![Sequent Microsystem 16 opto-insulated inputs HAT](/docs/seq-microsystem-optoisolated-hat.png?raw=true "Sequent Microsystem 16 opto-insulated inputs HAT")

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
A couple of suggested hats exposing relays are:

![SeenGreat 2CH output opto-insulated relay HAT](/docs/seengreat-2ch-relay.png?raw=true "SeenGreat 2CH output opto-insulated relay HAT")

* [SeenGreat 2CH output opto-insulated relay HAT](https://seengreat.com/wiki/107/).

![Sunfounder 4CH output opto-insulated relay HAT](/docs/sunfounder-4ch-relay.png?raw=true "Sunfounder 4CH output opto-insulated relay HAT")

* [Sunfounder 4 Channel 5V Relay Module](http://wiki.sunfounder.cc/index.php?title=4_Channel_5V_Relay_Module).

## Software prerequisites

* you must have an **MQTT broker** running somewhere (e.g. a Mosquitto broker);
* **Python >= 3.11**; for Raspberry it means you must be using Debian bookworm 12 or [Raspberry Pi OS](https://www.raspberrypi.com/software/operating-systems/) 12 or higher;
* there is no particular constraint on the [Home Assistant](https://www.home-assistant.io/) version, even if the project is continuously tested almost only against the latest Home Assistant version available.
