import asyncio

import yaml
from bleak import BleakClient, BleakError, BleakScanner
import datetime
import sys


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
            print(f"{timestamp()} Sending command: {command}")
            await self.client.write_gatt_char(self.config["gatt_char_uuid"], command, response=False)
        except BleakError as e:
            print(f"{timestamp()} BleakError: {e}, Command failed. Reestablishing connection.")
            await self.led_connect_loop()
            await self.send_command(command)

    async def discover_device(self):
        return await BleakScanner.find_device_by_address(self.config["led_mac"],
                                                         timeout=self.config["connection_timeout_sec"])

    async def led_connect_loop(self):
        for _ in range(int(self.config["connection_retries"])):
            try:
                await self.__led_connect()
                break
            except Exception as e:
                print(
                    f"{timestamp()} Could not connect to BLE LED. Error: {e}\nIs there an existing or old connection? Try restarting bluetooth.",
                    file=sys.stderr)

    async def await_connection(self):
        for _ in range(3):
            try:
                await self.client.connect(timeout=self.config["connection_timeout_sec"])
                break
            except Exception as e:
                print(f"{timestamp()} BLE Device Service unavailable ({e}). Trying again.", file=sys.stderr)

    async def __led_connect(self) -> None:
        print(f"{timestamp()} Connecting to BLE LED strip.")
        device = await self.discover_device()
        if device is None:
            raise BleakError("Discovery of BLE device failed")
        print(f"{timestamp()} Device discovered.")
        self.client = BleakClient(device)
        await self.await_connection()

        if self.client.is_connected:
            print(f"{timestamp()} Connected!")
        else:
            raise ConnectionError(
                f"{timestamp()} BLE Connection to {self.config["led_mac"]} failed after several retries.")
        if self.client.is_connected:
            print(f"{timestamp()} Connected!")
        else:
            raise ConnectionError(f"{timestamp()} BLE Connection to {self.config['led_mac']} failed after several retries.")

    async def choose_color_change(self):
        color = askcolor()[1]
        color = "ff0000" if color is None else str(color).replace("#", "").strip()
        await self.send_command(color_command(rgb_hex=color))

    async def close(self) -> None:
        await self.client.disconnect()
        return

    async def schedule_cleanup(self) -> None:
        await self.signal_received.wait()
        print(f"{timestamp()} Cleaning up.")
        await self.send_command(power_command(turnOn=False))
        await self.client.disconnect()

    async def schedule_poweroff(self, minutes):
        await self.send_command(sync_time_command())
        await asyncio.sleep(3)
        await self.send_command(schedule_off_command(minutes=minutes))
