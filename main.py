import random
from functools import partial
from tkinter.colorchooser import askcolor
from collections.abc import Callable

from elkbledom_byte_commands import *

instructions = """Instructions:
                Random color change - Press ENTER
                Turn off LED - Type "off" to turn off LED.
                Turn on LED - Type "on" to turn on the LED.
                Help Page - Type "help" to show this menu.
                To quit this program press CTRL + C (turns off LED) or type "q" to exit without doing anything.
"""
run_main_loop = True


async def color_change():
    color = askcolor()[1]
    color = "ff0000" if color is None else str(color).replace("#", "").strip()
    await send_command(color_command(rgb_hex=color))


def quit_main_loop():
    global run_main_loop
    run_main_loop = False


async_command_map: dict[str, Callable[[], any]] = {
    "off": partial(send_command, power_command(turnOn=False)),
    "on": partial(send_command, power_command(turnOn=True)),
    "c": color_change,
    "help": partial(print, instructions),
    "q": quit_main_loop,
    "": partial(send_command, color_command(rgb_hex=random.randbytes(3).hex())),
}


async def parse_instr(instr: str) -> Callable[[], any]:
    command = instr.strip().split(" ")
    for key in async_command_map:
        if key in command[0]:
            return async_command_map[key]
    return partial(print, f"Unknown command: {instr}")


async def main():
    print(f"{timestamp()} Using config parameters: {config}")
    await led_connect_loop()
    try:
        print(instructions)
        while run_main_loop:
            instr = input("> ")
            command_call = await parse_instr(instr)
            await command_call()
    finally:
        signal_received.set()


if __name__ == "__main__":
    asyncio.run(main())
