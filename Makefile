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

SHELL = /bin/bash

ifeq ($(BINDEST),)
BINDEST=/root
endif
ifeq ($(CFGDEST),)
CFGDEST=/etc
endif
ifeq ($(SYSTEMDUNITDEST),)
SYSTEMDUNITDEST=/lib/systemd/system/
endif

raspbian_install:
	# check OS version
	@if [[ `lsb_release -i -s` != "Raspbian" ]] || (( `lsb_release -r -s` < 12 )); then \
		echo ; \
		echo "** WARNING **" ; echo "THIS SOFTWARE HAS BEEN TESTED ONLY ON RASPBIAN 12 OR HIGHER AND REQUIRES PYTHON3.11" ; \
		echo "CHECK IF THIS DISTRIBUTION IS OK... PROCEEDING BUT EXPECT ERRORS" ; \
		echo ; \
	fi
	# install python venv
	python3 -m venv $(BINDEST)/ha-alarm-raspy2mqtt-venv
	$(BINDEST)/ha-alarm-raspy2mqtt-venv/bin/pip3 install .
	# install app config (only if MISSING, don't overwrite customizations)
	cp -av --update config.yaml $(CFGDEST)/ha-alarm-raspy2mqtt.yaml
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

raspbian_update_dependencies:
	$(BINDEST)/ha-alarm-raspy2mqtt-venv/bin/pip3 install --upgrade .
