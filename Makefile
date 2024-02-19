#
# This Makefile can be used to install this project on a Raspbian OS.
# The specifics of Raspbian OS are that:
#  * pip3 install <module-name> will not work and fail with msg:
#     "error: externally-managed-environment [...]"
#
# So this makefile takes care of automating
#  * creation of venv
#  * installation of this project into that venv
#  * distribution of config file in standard system folders

ifeq ($(BINDEST),)
BINDEST=/root
endif
ifeq ($(CFGDEST),)
CFGDEST=/etc
endif
ifeq ($(CFGDEST),)
SYSTEMDUNITDEST=/lib/systemd/system/
endif

raspbian_install:
	# install python
	python3 -m venv $(BINDEST)/ha-alarm-raspy2mqtt-venv
	$(BINDEST)/ha-alarm-raspy2mqtt-venv/bin/pip3 install .
	# install app config (only if MISSING, don't overwrite customizations)
	cp -av --update=none config.yaml $(CFGDEST)/ha-alarm-raspy2mqtt.yaml
	# install systemd config
	chmod 644 systemd/*.service
	cp -av systemd/*.service $(SYSTEMDUNITDEST)/

raspbian_enable_at_boot:
	systemctl daemon-reload
	systemctl enable ha-alarm-raspy2mqtt.service

raspbian_start:
	systemctl start ha-alarm-raspy2mqtt.service

raspbian_show_logs:
	journalctl -u ha-alarm-raspy2mqtt
