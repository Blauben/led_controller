import asyncio
import datetime
import logging
import sys
import tkinter as tk
from tkinter.colorchooser import askcolor

import yaml
from bleak import BleakClient, BleakError, BleakScanner
from docopt import extras

logger = logging.getLogger(__name__)


def timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S")


def color_command(rgb_hex: str) -> bytes:
    return bytes.fromhex(f"7e070503{rgb_hex}10ef")


def power_command(turnOn: bool) -> bytes:
    return bytes.fromhex("7e0404f00001ff00ef" if turnOn else "7e0404000000ff00ef")


def brightness_command(brightness: str = "100") -> bytes:
    return bytes.fromhex(f"7e0001{min(int(brightness), 100):02x}00000000ef")


def schedule_off_command(minutes: str = "60", disable=False) -> bytes:
    offtime = datetime.datetime.now() + datetime.timedelta(minutes=int(minutes))
    return bytes.fromhex(f"7e0082{offtime.hour:02x}{offtime.minute:02x}0001{255 if not disable else 127:02x}ef")


def sync_time_command() -> bytes:
    offtime = datetime.datetime.now()
    return bytes.fromhex(
        f"7e0083{offtime.hour:02x}{offtime.minute:02x}{offtime.second:02x}{offtime.isoweekday():02x}00ef")


def pick_color_hex() -> str | None:
    root = tk.Tk()
    root.withdraw()
    try:
        # Force the modal dialog to the foreground so it is not hidden behind the terminal.
        root.attributes("-topmost", True)
        root.update_idletasks()
        root.lift()
        _, color_hex = askcolor(parent=root, title="Choose LED color")
        return color_hex
    finally:
        root.destroy()


class LEDDriver:
    config: dict
    signal_received = asyncio.Event()
    client: BleakClient | None

    def __init__(self, config_file="config.yml"):
        self.setup(config_file)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def setup(self, config_file):
        self.config = yaml.safe_load(open(config_file, "r").read())
        asyncio.create_task(self.schedule_cleanup())

    async def send_command(self, command: bytes) -> None:
        try:
            logger.debug(f"Sending command: {command}")
            await self.client.write_gatt_char(self.config["gatt_char_uuid"], command, response=False)
        except BleakError as e:
            logger.warning("Command failed. Reestablishing connection: %s", e)
            await self.led_connect_loop()
            await self.send_command(command)

    async def discover_device(self):
        return await BleakScanner.find_device_by_address(self.config["led_mac"],
                                                         timeout=self.config["connection_timeout_sec"])

    async def led_connect_loop(self):
        max_retries = int(self.config["connection_retries"])
        logger.info(f"Connecting to BLE LED strip.")
        for retry in range(max_retries):
            try:
                await self.__led_connect()
                break
            except Exception as e:
                logger.error(
                    "Could not connect to BLE LED. Is there an existing or old connection? "
                    "Try restarting bluetooth. retry=%d/%d error=%s",
                    retry + 1,
                    max_retries,
                    e,
                )

    async def await_connection(self):
        total_retries = 3
        for retry in range(total_retries):
            try:
                await self.client.connect(timeout=self.config["connection_timeout_sec"])
                break
            except Exception as e:
                logger.warning(
                    "BLE Device Service unavailable. retry=%d/%d error=%s",
                    retry + 1,
                    total_retries,
                    e,
                )


    async def __led_connect(self) -> None:
        device = await self.discover_device()
        if device is None:
            raise BleakError("Discovery of BLE device failed")
        logger.info(f"Device discovered.")
        self.client = BleakClient(device)
        await self.await_connection()

        if self.client.is_connected:
            logger.info(f"Connected!")
        else:
            err_msg = f"BLE Connection to {self.config["led_mac"]} failed after several retries."
            logger.error(err_msg)
            raise ConnectionError(err_msg)

    async def choose_color_change(self):
        try:
            color = pick_color_hex()
        except tk.TclError as e:
            logger.error("Color picker could not be opened: %s", e)
            return

        color = "ff0000" if color is None else str(color).replace("#", "").strip()
        await self.send_command(color_command(rgb_hex=color))

    async def close(self) -> None:
        await self.client.disconnect()
        return

    async def schedule_cleanup(self) -> None:
        await self.signal_received.wait()
        logger.info("Cleaning up.")
        await self.send_command(power_command(turnOn=False))
        await self.client.disconnect()

    async def schedule_poweroff(self, minutes):
        await self.send_command(sync_time_command())
        await asyncio.sleep(3)
        await self.send_command(schedule_off_command(minutes=minutes))
