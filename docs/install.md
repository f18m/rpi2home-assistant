# Installation

This section focuses on how to install on a Raspberry Pi with Debian Bookworm 12.

## Using `git` and `make`

The [Raspberry Pi OS](https://www.raspberrypi.com/software/operating-systems/) does not allow to install Python software using `pip`.
Trying to install a Python package that way leads to an error like:

```sh
error: externally-managed-environment [...]
```

That means that to install Python software, a virtual environment has to be used.
This procedure automates the creation of the venv and has been tested on Raspberry Pi OS 12 (bookworm). 
Just copy-paste on your raspberry each command:

```sh
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

## Using Pypi and `pip`

This project is packaged as a Python wheel at https://pypi.org/project/rpi2home-assistant/.
This makes it possible to install rpi2home-assistant using `pip`.
The procedure relies also in this case on the creation of a venv:

```sh
apt install python3-venv
python3 -m venv rpi2home-assistant-venv
source rpi2home-assistant-venv/bin/activate
pip3 install rpi2home-assistant
```

## Deploy/test with Docker

This project also provides a multi-arch docker image to ease testing.
You can launch this software into a docker container by running:

```sh
docker run -d \
   --volume <your config file>:/etc/rpi2home-assistant.yaml \
   --privileged --hostname $(hostname) \
   ghcr.io/f18m/rpi2home-assistant:<latest version>
```

However please note that using Docker on a Raspberry PI is probably an overkill for this application,
so the preferred way to save CPU is to install using a dedicated Python venv (see above).
