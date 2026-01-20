#!/usr/bin/env python3

import time
import asyncio

# from raspy2mqtt.constants import *
from .config import AppConfig

#
# Author: fmontorsi
# Created: Apr 2024
# License: Apache license
#

# =======================================================================================================
# StatsCollector
# =======================================================================================================


class StatsCollector:
    """
    This class handles collecting stats from other objects of the application and periodically
    show them on the stdout
    """

    # the stop-request is not related to a particular instance of this class... it applies to any instance
    stop_requested = False

    def __init__(self, objs_with_stats: list):
        self.start_time = time.time()
        self.counter = 1
        self.objs_with_stats = objs_with_stats

    async def print_stats_periodically(self, cfg: AppConfig):
        if cfg.stats_log_period_sec == 0:
            return  # the user requested to NOT print periodically the stats
        next_stat_time = time.time() + cfg.stats_log_period_sec
        while not StatsCollector.stop_requested:
            # Print out stats to help debugging
            if time.time() >= next_stat_time:
                self.print_stats()
                next_stat_time = time.time() + cfg.stats_log_period_sec

            await asyncio.sleep(0.25)

    def print_stats(self):
        print(f">> STAT REPORT #{self.counter}")

        uptime_sec = time.time() - self.start_time
        m, s = divmod(uptime_sec, 60)
        h, m = divmod(m, 60)
        h = int(h)
        m = int(m)
        s = int(s)
        print(f">> Uptime: {h}:{m:02}:{s:02}")

        for x in self.objs_with_stats:
            x.print_stats()

        self.counter += 1
