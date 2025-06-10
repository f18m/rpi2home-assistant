#!/usr/bin/env python3

#
# Author: fmontorsi
# Created: Feb 2024
# License: Apache license
#
# TODO: add HomeAssistant discovery messages

import argparse
import os
import fcntl
import sys
import asyncio
import gpiozero
import subprocess
import signal
from .stats import StatsCollector
from .constants import SeqMicroHatConstants, MiscAppDefaults
from .config import AppConfig
from .optoisolated_inputs_handler import OptoIsolatedInputsHandler
from .gpio_inputs_handler import GpioInputsHandler
from .gpio_outputs_handler import GpioOutputsHandler
from .homeassistant_status_tracker import HomeAssistantStatusTracker

# =======================================================================================================
# GLOBALs
# =======================================================================================================

# sets to True when the application was asked to exit:
g_stop_requested = False


# =======================================================================================================
# MAIN HELPERS
# =======================================================================================================


def parse_command_line():
    """Parses the command line and returns the configuration as dictionary object."""
    parser = argparse.ArgumentParser(
        description=f"Utility to expose the {SeqMicroHatConstants.MAX_CHANNELS} digital inputs read by Raspberry over MQTT, to ease their integration as (binary) sensors in Home Assistant."
    )

    # Optional arguments
    # NOTE: we cannot add required=True to --output option otherwise it's impossible to invoke this tool with just --version
    parser.add_argument(
        "-c",
        "--config",
        help=f"YAML file specifying the software configuration. Defaults to '{MiscAppDefaults.CONFIG_FILE}'",
        default=MiscAppDefaults.CONFIG_FILE,
    )
    parser.add_argument(
        "-d",
        "--disable-hw",
        help="This is mostly a debugging option; it disables interactions with HW components to ease integration tests",
        action="store_true",
        default=False,
    )
    parser.add_argument("-v", "--verbose", help="Be verbose.", action="store_true", default=False)
    parser.add_argument(
        "-V",
        "--version",
        help="Print version and exit",
        action="store_true",
        default=False,
    )

    if "COLUMNS" not in os.environ:
        os.environ["COLUMNS"] = "120"  # avoid too many line wraps
    args = parser.parse_args()

    if args.version:
        cfg = AppConfig()
        print(f"Version: {cfg.app_version}")
        sys.exit(0)

    return args


def instance_already_running(label="default"):
    """
    Detect if an an instance with the label is already running, globally
    at the operating system level.

    Using `os.open` ensures that the file pointer won't be closed
    by Python's garbage collector after the function's scope is exited.

    The lock will be released when the program exits, or could be
    released if the file pointer were closed.
    """

    try:
        lock_file_pointer = os.open(f"/tmp/instance_{label}.lock", os.O_WRONLY | os.O_CREAT)
    except PermissionError as e:
        print(f"Not enough permissions to write files under /tmp. Run this application as root: {e}")
        sys.exit(4)

    try:
        # LOCK_NB = lock non-blocking
        # LOCK_EX = exclusive lock
        fcntl.lockf(lock_file_pointer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        already_running = False
    except IOError:
        already_running = True

    return already_running


def shutdown():
    print("!! Detected long-press on the Sequent Microsystem button. Triggering clean shutdown of the Raspberry PI !!")
    subprocess.call(["sudo", "shutdown", "-h", "now"])


def init_hardware(cfg: AppConfig):
    if cfg.disable_hw:
        return []

    # setup GPIO connected to the pushbutton (input) and
    # assign the when_held function to be called when the button is held for more than 5 seconds
    # (NOTE: the way gpiozero works is that a new thread is spawned to listed for this event on the Raspy GPIO)
    if "GPIOZERO_PIN_FACTORY" in os.environ:
        print(f"GPIO factory backend is: {os.environ['GPIOZERO_PIN_FACTORY']}")
    else:
        print(
            "GPIO factory backend is the default one. This might fail on newer Raspbian versions with Linux kernel >= 6.6.20"
        )

    try:
        gpiozero.Device.ensure_pin_factory()
    except gpiozero.exc.BadPinFactory:
        print("Unable to load a gpiozero pin factory. Typically this happens if you don't have pigpio installed.")
        print("Alternatively you can run this software for basic testing exporting the env variable DISABLE_HW.")

    buttons = []
    print("Initializing SequentMicrosystem GPIO shutdown button")
    b = gpiozero.Button(SeqMicroHatConstants.SHUTDOWN_BUTTON_GPIO, hold_time=5)
    b.when_held = shutdown
    buttons.append(b)

    return buttons


# =======================================================================================================
# ASYNC HELPERS
# =======================================================================================================


async def signal_handler(sig: signal.Signals) -> None:
    global g_stop_requested
    g_stop_requested = True
    print(f"Received signal {sig.name}... stopping all async tasks")


async def main_loop():
    global g_stop_requested

    cfg = AppConfig()
    print(f"{MiscAppDefaults.THIS_APP_NAME} version {cfg.app_version} starting")

    args = parse_command_line()

    if not cfg.load(args.config):
        return 1  # invalid config file... abort with failure exit code

    cfg.merge_options_from_cli(args)
    cfg.merge_options_from_env_vars()
    cfg.print_config_summary()

    # install signal handler
    loop = asyncio.get_running_loop()
    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, lambda: asyncio.create_task(signal_handler(sig)))

    # initialize handlers
    opto_inputs_handler = OptoIsolatedInputsHandler()
    gpio_inputs_handler = GpioInputsHandler()
    gpio_outputs_handler = GpioOutputsHandler()
    homeassistant_status_tracker = HomeAssistantStatusTracker()
    stats_collector = StatsCollector([opto_inputs_handler, gpio_inputs_handler, gpio_outputs_handler])

    button_instances = init_hardware(cfg)
    button_instances += opto_inputs_handler.init_hardware(cfg)
    button_instances += gpio_inputs_handler.init_hardware(cfg, loop)
    gpio_outputs_handler.init_hardware(cfg)

    homeassistant_status_tracker.set_discovery_publish_coroutines(
        [
            opto_inputs_handler.homeassistant_discovery_message_publish,
            gpio_outputs_handler.homeassistant_discovery_message_publish,
        ]
    )

    # wrap with error-handling code the main loop
    exit_code = 0
    print("Starting main loop")
    while not g_stop_requested:
        # the double-nested 'try' is the only way I found in Python 3.11.2 to catch properly
        # both exception groups (using the 'except*' syntax) and also have a default catch-all
        # label using regular 'except' syntax.

        # NOTE: unfortunately we cannot use a taskgroup: the problem is the function
        # subscribe_and_activate_outputs() which uses the aiomqtt.Client.messages generator
        # which does not allow to easily stop the 'waiting for next message' operation.
        # This means we need to create each task manually with asyncio.EventLoop.create_task()
        # and cancel() them whenever a SIGTERM is received.
        #
        # async with asyncio.TaskGroup() as tg:
        #     tg.create_task(print_stats_periodically(cfg))
        #     # inputs:
        #     tg.create_task(publish_optoisolated_inputs(cfg))
        #     tg.create_task(process_gpio_inputs_queue_and_publish(cfg))
        #     # outputs:
        #     tg.create_task(subscribe_and_activate_outputs(cfg))
        #     tg.create_task(publish_outputs_state(cfg))

        # launch all coroutines:
        loop = asyncio.get_running_loop()
        tasks = [
            loop.create_task(stats_collector.print_stats_periodically(cfg)),
            loop.create_task(opto_inputs_handler.publish_optoisolated_inputs(cfg)),
            loop.create_task(gpio_inputs_handler.process_gpio_inputs_queue_and_publish(cfg)),
            loop.create_task(gpio_outputs_handler.subscribe_and_activate_outputs(cfg)),
            loop.create_task(gpio_outputs_handler.publish_outputs_state(cfg)),
        ]

        if cfg.homeassistant_discovery_messages_enable:
            # subscribe to HomeAssistant status notification and eventually trigger MQTT discovery messages
            loop.create_task(homeassistant_status_tracker.subscribe_status(cfg)),

        # this main coroutine will simply wait till a SIGTERM arrives and
        # we get g_stop_requested=True:
        while not g_stop_requested:
            await asyncio.sleep(1)

        print("Main coroutine is now cancelling all sub-tasks (coroutines)")
        GpioInputsHandler.stop_requested = True
        GpioOutputsHandler.stop_requested = True
        OptoIsolatedInputsHandler.stop_requested = True
        for t in tasks:
            t.cancel()

        print("Waiting cancellation of all tasks")
        for t in tasks:
            # Wait for the task to be cancelled
            try:
                await t
            except asyncio.CancelledError:
                pass

    print("Printing stats for the last time:")
    stats_collector.print_stats()

    print(f"Exiting gracefully with exit code {exit_code}...")
    return exit_code


def entrypoint():
    if instance_already_running(MiscAppDefaults.THIS_APP_NAME):
        print(
            "Sorry, detected another instance of this daemon is already running. Using the same I2C bus from 2 sofware programs is not recommended. Aborting."
        )
        sys.exit(3)

    try:
        sys.exit(asyncio.run(main_loop()))
    except KeyboardInterrupt:
        print("Stopping due to CTRL+C")


# =======================================================================================================
# MAIN
# =======================================================================================================

if __name__ == "__main__":
    entrypoint()
