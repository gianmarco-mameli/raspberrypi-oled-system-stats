#!/usr/bin/env python3
"""Display Raspberry Pi system stats (CPU, memory, storage, temperature) on a
128x32 I2C SSD1306 OLED display, with a slow pixel-orbiting shift to reduce
the risk of burn-in on the always-on display.

Designed to run as a systemd service (handles SIGTERM/SIGINT for clean stop).
"""

import shutil
import signal
import sys
import time

import psutil
from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from PIL import ImageFont

# --- Display configuration ---
I2C_PORT = 1
I2C_ADDRESS = 0x3C
DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 32

# --- Timing configuration ---
STATS_UPDATE_SECONDS = 2
ORBIT_SHIFT_SECONDS = 60

# --- Burn-in prevention: small (x, y) offsets cycled through over time ---
ORBIT_OFFSETS = [
    (0, 0), (1, 0), (2, 0), (2, 1), (2, 2),
    (1, 2), (0, 2), (-1, 2), (-2, 2), (-2, 1),
    (-2, 0), (-2, -1), (-2, -2), (-1, -2), (0, -1),
]

TEMP_PATH = "/sys/class/thermal/thermal_zone0/temp"

running = True


def handle_stop_signal(signum, frame):
    global running
    running = False


def get_cpu_load():
    return psutil.cpu_percent(interval=None)


def get_memory_usage():
    mem = psutil.virtual_memory()
    used_mb = mem.used // (1024 * 1024)
    total_mb = mem.total // (1024 * 1024)
    return used_mb, total_mb


def get_storage_usage():
    total, used, _free = shutil.disk_usage("/")
    used_gb = used / (1024 ** 3)
    total_gb = total / (1024 ** 3)
    return used_gb, total_gb


def get_cpu_temperature():
    try:
        with open(TEMP_PATH, "r") as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return 0.0


def draw_stats(draw, font, offset, stats):
    cpu, (mem_used, mem_total), (disk_used, disk_total), temp = stats
    x, y = offset

    line1 = f"CPU:{cpu:>4.1f}% {temp:>4.1f}C"
    line2 = f"MEM:{mem_used}/{mem_total}MB"
    line3 = f"DSK:{disk_used:.1f}/{disk_total:.1f}GB"

    draw.text((x, y), line1, font=font, fill="white")
    draw.text((x, y + 10), line2, font=font, fill="white")
    draw.text((x, y + 20), line3, font=font, fill="white")


def main():
    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)

    serial = i2c(port=I2C_PORT, address=I2C_ADDRESS)
    device = ssd1306(serial, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT)
    font = ImageFont.load_default()

    # prime cpu_percent so the first reading is meaningful
    psutil.cpu_percent(interval=None)

    last_stats_update = 0.0
    last_orbit_shift = 0.0
    orbit_index = 0
    stats = (0.0, (0, 0), (0.0, 0.0), 0.0)

    try:
        while running:
            now = time.monotonic()

            if now - last_stats_update >= STATS_UPDATE_SECONDS:
                stats = (
                    get_cpu_load(),
                    get_memory_usage(),
                    get_storage_usage(),
                    get_cpu_temperature(),
                )
                last_stats_update = now

            if now - last_orbit_shift >= ORBIT_SHIFT_SECONDS:
                orbit_index = (orbit_index + 1) % len(ORBIT_OFFSETS)
                last_orbit_shift = now

            with canvas(device) as draw:
                draw_stats(draw, font, ORBIT_OFFSETS[orbit_index], stats)

            time.sleep(1)
    finally:
        device.clear()
        device.hide()


if __name__ == "__main__":
    sys.exit(main())
