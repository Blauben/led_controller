import math
import os.path
import random
from datetime import date, datetime as dt
import time

import schedule
import signal
from functools import partial
from collections.abc import Callable

from elkbledom_byte_commands import *
from const import help_page, config_template
from util import get_sunset

run_main_loop = True


async def quit_main_loop():
    global run_main_loop
    run_main_loop = False


def async_command_map(driver: LEDDriver, *args: any) -> dict[str, Callable[[], any]]:
    return {
        "off": partial(driver.send_command, power_command(turnOn=False)),
        "on": partial(driver.send_command, power_command(turnOn=True)),
        "c": driver.choose_color_change,
        "s": partial(driver.schedule_poweroff, *args),
        "b": partial(driver.send_command, brightness_command(*args)),
        "help": partial(print, help_page),
        "q": quit_main_loop,
        "": partial(driver.send_command, color_command(rgb_hex=random.randbytes(3).hex())),
    }


async def parse_instr(driver: LEDDriver, instr: str) -> Callable[[], any]:
    command = instr.strip().split(" ")
    command_map = async_command_map(driver, *command[1:])
    for key in command_map:
        if command[0].startswith(key):
            return command_map[key]
    return partial(print, f"Unknown command: {instr}")


def generate_config():
    if os.path.exists("config.yml"):
        return

    with open("config.yml", "w") as f:
        f.write(config_template)
    print("Sample config generated. Please specify values.")
    exit(0)


def sighandler(driver, signum, frame):
    driver.signal_received.set()


def register_sighandlers(driver: LEDDriver):
    signal.signal(signal.SIGINT, partial(sighandler, driver))
    signal.signal(signal.SIGTERM, partial(sighandler, driver))


async def autostart_at_sunset_job(driver: LEDDriver):
    print("Starting LED")
    await async_command_map(driver)["on"]()
    now = dt.now()
    poweroff_minutes = max(30, 24 * 60 - (now.hour * 60 + now.minute))
    print("Powering off in", poweroff_minutes, "minutes")
    await async_command_map(driver, poweroff_minutes)["s"]()


async def run_autostart_at_sunset(driver: LEDDriver):
    sunset_time = dt.strptime(get_sunset(), "%I:%M:%S %p").time()
    sunset = dt.combine(date.today(), sunset_time)

    if dt.now() < sunset:
        wait_seconds = (sunset - dt.now()).total_seconds()
        print(f"{timestamp()} Scheduling autostart at sunset: {sunset} ({wait_seconds}s)")
        await asyncio.sleep(wait_seconds)

    await autostart_at_sunset_job(driver)


async def handle_cli_args(driver: LEDDriver):
    if "--autostart" in sys.argv:
        await run_autostart_at_sunset(driver)


async def main():
    generate_config()
    driver = LEDDriver()
    register_sighandlers(driver)
    print(f"{timestamp()} Using config parameters: {driver.config}")
    await driver.led_connect_loop()
    if len(sys.argv) > 1:
        await handle_cli_args(driver)
        return

    print(f"{help_page}\n")
    while run_main_loop:
        instr = input("> ")
        command_call = await parse_instr(driver, instr)
        try:
            await command_call()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
