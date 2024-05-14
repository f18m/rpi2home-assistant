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
import aiomqtt
import gpiozero
import subprocess
import signal
import time
from raspy2mqtt.stats import *
from raspy2mqtt.config import *
from raspy2mqtt.constants import *
from raspy2mqtt.optoisolated_inputs_handler import *
from raspy2mqtt.gpio_inputs_handler import *
from raspy2mqtt.gpio_outputs_handler import *

# =======================================================================================================
# GLOBALs
# =======================================================================================================

# sets to True when the application was asked to exit:
g_stop_requested = False


# =======================================================================================================
# MAIN HELPERS
# =======================================================================================================


def get_my_version():
    try:
        from importlib.metadata import version
    except:
        from importlib_metadata import version
    return version(THIS_SCRIPT_PYPI_PACKAGE)


def parse_command_line():
    """Parses the command line and returns the configuration as dictionary object."""
    parser = argparse.ArgumentParser(
        description=f"Utility to expose the {SEQMICRO_INPUTHAT_MAX_CHANNELS} digital inputs read by Raspberry over MQTT, to ease their integration as (binary) sensors in Home Assistant."
    )

    # Optional arguments
    # NOTE: we cannot add required=True to --output option otherwise it's impossible to invoke this tool with just --version
    parser.add_argument(
        "-c",
        "--config",
        help=f"YAML file specifying the software configuration. Defaults to '{DEFAULT_CONFIG_FILE}'",
        default=DEFAULT_CONFIG_FILE,
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
        print(f"Version: {get_my_version()}")
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

    lock_file_pointer = os.open(f"/tmp/instance_{label}.lock", os.O_WRONLY | os.O_CREAT)

    try:
        # LOCK_NB = lock non-blocking
        # LOCK_EX = exclusive lock
        fcntl.lockf(lock_file_pointer, fcntl.LOCK_EX | fcntl.LOCK_NB)
        already_running = False
    except IOError:
        already_running = True

    return already_running



# =======================================================================================================
# GPIOZERO helper functions
# These functions execute in the context of secondary threads created by gpiozero library
# and attached to INPUT button pressure
# =======================================================================================================


def shutdown():
    print(f"!! Detected long-press on the Sequent Microsystem button. Triggering clean shutdown of the Raspberry PI !!")
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
            f"GPIO factory backend is the default one. This might fail on newer Raspbian versions with Linux kernel >= 6.6.20"
        )

    buttons = []
    print(f"Initializing SequentMicrosystem GPIO shutdown button")
    b = gpiozero.Button(SEQMICRO_INPUTHAT_SHUTDOWN_BUTTON_GPIO, hold_time=5)
    b.when_held = shutdown
    buttons.append(b)

    return buttons


# =======================================================================================================
# ASYNC HELPERS
# =======================================================================================================

async def print_stats_periodically(cfg: AppConfig):
    global g_stop_requested
    # loop = asyncio.get_running_loop()
    next_stat_time = time.time() + cfg.stats_log_period_sec
    while not g_stop_requested:
        # Print out stats to help debugging
        if time.time() >= next_stat_time:
            print_stats()
            next_stat_time = time.time() + cfg.stats_log_period_sec

        await asyncio.sleep(0.25)


async def signal_handler(sig: signal.Signals) -> None:
    global g_stop_requested
    g_stop_requested = True
    print(f"Received signal {sig.name}... stopping all async tasks")
    # raise RuntimeError("Stopping via signal")


async def main_loop():
    global g_stats, g_stop_requested

    args = parse_command_line()
    cfg = AppConfig()
    if not cfg.load(args.config):
        return 1  # invalid config file... abort with failure exit code

    # merge CLI options into the configuration object:
    cfg.disable_hw = args.disable_hw
    cfg.verbose = args.verbose

    # merge env vars into the configuration object:
    if os.environ.get("DISABLE_HW", None) != None:
        cfg.disable_hw = True
    if os.environ.get("VERBOSE", None) != None:
        cfg.verbose = True
    if os.environ.get("MQTT_BROKER_HOST", None) != None:
        # this particular env var can override the value coming from the config file:
        cfg.mqtt_broker_host = os.environ.get("MQTT_BROKER_HOST")
    if os.environ.get("MQTT_BROKER_PORT", None) != None:
        # this particular env var can override the value coming from the config file:
        cfg.mqtt_broker_port = os.environ.get("MQTT_BROKER_PORT")

    cfg.print_config_summary()

    # install signal handler
    loop = asyncio.get_running_loop()
    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, lambda: asyncio.create_task(signal_handler(sig)))

    # initialize handlers
    opto_inputs_handler = OptoIsolatedInputsHandler()
    gpio_inputs_handler = GpioInputsHandler()
    gpio_outputs_handler = GpioOutputsHandler()

    button_instances = init_hardware(cfg)
    button_instances += opto_inputs_handler.init_hardware(cfg, loop)
    button_instances += gpio_inputs_handler.init_hardware(cfg)
    gpio_outputs_handler.init_hardware(cfg)

    # wrap with error-handling code the main loop
    exit_code = 0
    print(f"Starting main loop")
    while not g_stop_requested:
        # the double-nested 'try' is the only way I found in Python 3.11.2 to catch properly
        # both exception groups (using the 'except*' syntax) and also have a default catch-all
        # label using regular 'except' syntax.
        try:
            try:
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
                    loop.create_task(print_stats_periodically(cfg)),
                    loop.create_task(opto_inputs_handler.publish_optoisolated_inputs(cfg)),
                    loop.create_task(gpio_inputs_handler.process_gpio_inputs_queue_and_publish(cfg)),
                    loop.create_task(gpio_outputs_handler.subscribe_and_activate_outputs(cfg)),
                    loop.create_task(gpio_outputs_handler.publish_outputs_state(cfg)),
                ]

                # this main coroutine will simply wait till a SIGTERM arrives and
                # we get g_stop_requested=True:
                while not g_stop_requested:
                    await asyncio.sleep(1)

                print("Main coroutine is now cancelling all sub-tasks (coroutines)")
                for t in tasks:
                    t.cancel()

                print("Waiting cancellation of all tasks")
                for t in tasks:
                    # Wait for the task to be cancelled
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass

            except* aiomqtt.MqttError as err:
                print(
                    f"Connection lost: {err.exceptions}; reconnecting in {cfg.mqtt_reconnection_period_sec} seconds ..."
                )
                g_stats["num_connections_lost"] += 1
                await asyncio.sleep(cfg.mqtt_reconnection_period_sec)
            except* KeyboardInterrupt:
                print_stats()
                print("Stopped by CTRL+C... aborting")
                g_stop_requested = True
                exit_code = 1
        except ExceptionGroup as e:
            # this is very important... it's the 'default' case entered whenever an exception does
            # not match any of the more specific 'except' clauses above
            # IMPORTANT: this seems to work correctly/as-expected only in Python >=3.11.4 (including 3.12)
            # see this note: https://docs.python.org/3/whatsnew/3.12.html, which contains something that might be related:
            #  'When a try-except* construct handles the entire ExceptionGroup and raises one other exception,
            #   that exception is no longer wrapped in an ExceptionGroup.
            #   Also changed in version 3.11.4. (Contributed by Irit Katriel in gh-103590.)'
            print(f"Got exception of type [{e}], which is unhandled.")
            g_stop_requested = True
            exit_code = 2
        except Exception as e:
            print(f"Got exception of type [{e}], which is unhandled.")
            g_stop_requested = True
            exit_code = 2

    print(f"Exiting gracefully with exit code {exit_code}... printing stats for the last time:")
    print_stats()
    return exit_code


def main():
    if instance_already_running("ha-alarm-raspy2mqtt"):
        print(
            f"Sorry, detected another instance of this daemon is already running. Using the same I2C bus from 2 sofware programs is not recommended. Aborting."
        )
        sys.exit(3)

    print(f"{THIS_SCRIPT_PYPI_PACKAGE} version {get_my_version()} starting")
    try:
        sys.exit(asyncio.run(main_loop()))
    except KeyboardInterrupt:
        print(f"Stopping due to CTRL+C")


# =======================================================================================================
# MAIN
# =======================================================================================================

if __name__ == "__main__":
    main()
