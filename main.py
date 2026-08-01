import argparse
import os.path
import random
from datetime import date, datetime as dt

import logging.handlers
import re
import signal
from functools import partial
from collections.abc import Callable, Awaitable
from typing import Any
from dataclasses import dataclass

from LED_Driver import *
from const import config_template
from util import get_sunset

run_main_loop = True

handlers = [
    logging.StreamHandler(),
    logging.handlers.TimedRotatingFileHandler(
        "LED_Controller.log", when="midnight", backupCount=2
    ),
]
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s",
    handlers=handlers,
)

logger = logging.getLogger("LED_Controller_main")

CommandHandler = Callable[[], Awaitable[Any]]


@dataclass(frozen=True)
class CommandEntry:
    doc: str
    command: CommandHandler


async def quit_main_loop():
    global run_main_loop
    run_main_loop = False


async def print_message(message: str) -> None:
    print(message)


def build_help_page(command_map: dict[str, CommandEntry]) -> str:
    lines = ["LED Controller Commands:", ""]
    for key, entry in command_map.items():
        command_name = "<enter>" if key == "" else key
        lines.append(f"  {command_name:<10} {entry.doc}")
    return "\n".join(lines)


def async_command_map(driver: LEDDriver, *args: Any) -> dict[str, CommandEntry]:
    random_color = CommandEntry(
        "Send a random color",
        partial(driver.send_command, color_command(rgb_hex=random.randbytes(3).hex())),
    )
    command_map: dict[str, CommandEntry] = {
        "off": CommandEntry(
            "Turn the LED off",
            partial(driver.send_command, power_command(turnOn=False)),
        ),
        "on": CommandEntry(
            "Turn the LED on", partial(driver.send_command, power_command(turnOn=True))
        ),
        "c": CommandEntry("Open the color picker dialog", driver.choose_color_change),
        "s": CommandEntry(
            "Schedule power-off in <minutes>", partial(driver.schedule_poweroff, *args)
        ),
        "b": CommandEntry(
            "Set brightness to <0-100>",
            partial(driver.send_command, brightness_command(*args)),
        ),
        "q": CommandEntry("Quit the controller", quit_main_loop),
        "": random_color,
        "r": random_color,
    }
    command_map["help"] = CommandEntry(
        "Show this help page", partial(print_message, build_help_page(command_map))
    )
    return command_map


async def parse_instr(driver: LEDDriver, instr: str) -> CommandHandler:
    """Parses the instruction and returns the corresponding command function. If the instruction is not recognized, returns a function that prints an error message. The returned function is not executed in this function, but intended to be awaited in the caller function."""
    command = instr.strip().split(" ")
    command_map = async_command_map(driver, *command[1:])
    for key, entry in command_map.items():
        if command[0].startswith(key):
            logger.debug(f"Received command: {key}")
            return entry.command
    logger.warning(f"Received unrecognized command: {instr}")
    return partial(
        print_message, f"Unknown command: {instr}\n\n{build_help_page(command_map)}"
    )


def generate_config():
    if os.path.exists("config.yml"):
        return

    with open("config.yml", "w") as f:
        f.write(config_template)
    logger.info("Sample config generated. Please specify values.")
    exit(0)


def sighandler(driver, signum, frame):
    driver.signal_received.set()


def register_sighandlers(driver: LEDDriver):
    signal.signal(signal.SIGINT, partial(sighandler, driver))
    signal.signal(signal.SIGTERM, partial(sighandler, driver))


async def autostart_at_sunset_job(driver: LEDDriver, args: argparse.Namespace):
    await async_command_map(driver)["on"].command()
    if args.randomize:
        await async_command_map(driver)["r"].command()
    now = dt.now()
    poweroff_minutes = max(30, 24 * 60 - (now.hour * 60 + now.minute))
    logger.info("Powering off in %d minutes", poweroff_minutes)
    await async_command_map(driver, poweroff_minutes)["s"].command()


async def run_autostart_at_sunset(driver: LEDDriver, args: argparse.Namespace):
    sunset_time = dt.strptime(get_sunset(), "%I:%M:%S %p").time()
    sunset = dt.combine(date.today(), sunset_time)
    logger.debug("Sunset time: %s", sunset)

    if dt.now() < sunset:
        wait_seconds = (sunset - dt.now()).total_seconds()
        logger.info(
            "Scheduling autostart at sunset: sunset=%s wait_seconds=%.0f",
            sunset,
            wait_seconds,
        )
        await asyncio.sleep(wait_seconds)

    await autostart_at_sunset_job(driver, args)


async def execute_instr(driver: LEDDriver, instr: str):
    command_call = await parse_instr(driver, instr)
    try:
        await command_call()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Exiting...")
        exit(0)
    except Exception as e:
        logger.exception("Unhandled exception! Continuing: %s", e)
        pass


async def handle_cli_args(driver: LEDDriver, args: argparse.Namespace):
    if args.autostart:
        await run_autostart_at_sunset(driver, args)


async def cli_loop(driver: LEDDriver):
    print(f"{build_help_page(async_command_map(driver))}\n")
    while run_main_loop:
        instr = input("> ")
        await execute_instr(driver, instr)


async def parse_stdin_stream(driver: LEDDriver, instructions: str = ""):
    pruned_instructions = (
        re.sub(r"\s+", " ", instructions)
        .replace("\n", "")
        .replace("\r", "")
        .replace('"', "")
        .replace("'", "")
    )
    for instr in pruned_instructions.split(";"):
        instr = instr.strip()
        if instr == "":
            continue
        await execute_instr(driver, instr)


async def argparser(driver: LEDDriver):
    parser = argparse.ArgumentParser(
        prog="LED_Controller",
        description="This program is a BLE LED Controller for ELKBLE-DOM LED devices. This program allows you to control the LED device via command-line interface (CLI) or by piping commands directly into the program as well as functioning as an autostart daemon to start the LED at sunset.",
        epilog=f"""\
    If no arguments are provided, the program will enter an interactive command-line interface (CLI) mode.
    In this mode, you can enter commands to control the LED device.
    Commands can be entered one at a time, or multiple commands can be separated by semicolons (;).

    Alternatively, you can pipe commands seperated by semicolons (;) directly into the program. For example:
    echo "on; s 60; c" | python main.py

    {build_help_page(async_command_map(driver))}

    Authored by: Ben Frauenknecht""",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--autostart",
        action="store_true",
        help="Automatically start the LED at sunset and schedule power-off at midnight.",
    )
    parser.add_argument(
        "--randomize",
        action="store_true",
        help="Randomize the LED color on startup. This option is only effective when used with --autostart.",
    )
    return parser.parse_args()


async def main():
    driver = LEDDriver()
    args = await argparser(driver)
    logger.info("Starting LED Controller")
    generate_config()
    logger.info("Using config parameters: %s", driver.config)
    register_sighandlers(driver)
    await driver.led_connect_loop()
    if not sys.stdin.isatty():
        logger.debug(f"Reading from stdin...")
        instr = sys.stdin.read()
        logger.debug(
            f"Received piped data: %s. Treating as instruction and exiting...", instr
        )
        await parse_stdin_stream(driver, instr)
    elif len(sys.argv) > 1:
        await handle_cli_args(driver, args)
    else:
        await cli_loop(driver)
    logger.info("Exiting...")


if __name__ == "__main__":
    asyncio.run(main())
