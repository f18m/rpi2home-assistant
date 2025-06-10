# Development

This section contains information useful in case you want to hack/collaborate on the project.
Patches/improvements and new features are welcome.

This project uses `hatch` as build system (https://hatch.pypa.io/) so the 'build' is as simple as:

```sh
python3 -m build
```

To develop changes you can create a branch and push changes there. Then:

```sh
make format
make lint
make docker
make unit-test
make integration-test
```

To validate locally your changes.

Finally, once ready, check out your branch on your raspberry and then run:

```sh
python3 -m venv ~/rpi2home-assistant-venv
~/rpi2home-assistant-venv/bin/pip3 install .
source ~/rpi2home-assistant-venv/bin/activate
cd <checkout_folder>/raspy2mqtt
./raspy2mqtt -c /etc/rpi2home-assistant.yaml
```

Alternatively you can test manually on your local machine by running:

```sh
make run-mosquitto

nano myconfig.yaml # stick the Mosquitto port exposed locally inside the config file
make run-docker CONFIG_FILE_FOR_DOCKER=myconfig.yaml
```

