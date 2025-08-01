import asyncio
import signal

import yaml
from bleak import BleakClient, BleakError, BleakScanner
import datetime
import sys

# Load config from the yaml file
config = yaml.safe_load(open("config.yml", "r").read())
signal_received = asyncio.Event()
cleanup_scheduled = False

client: BleakClient | None = None


async def send_command(command: bytes) -> None:
    global client
    try:
        print(f"{timestamp()} Sending command: {command}")
        await client.write_gatt_char(config["gatt_char_uuid"], command, response=False)
    except BleakError as e:
        print(f"{timestamp()} BleakError: {e}, Command failed. Reestablishing connection.")
        await led_connect_loop()
        await send_command(command)


def color_command(rgb_hex: str) -> bytes:
    return bytes.fromhex(f"7e070503{rgb_hex}10ef")


def power_command(turnOn: bool) -> bytes:
    return bytes.fromhex("7e0404f00001ff00ef" if turnOn else "7e0404000000ff00ef")


async def discover_device():
    return await BleakScanner.find_device_by_address(config["led_mac"], timeout=config["connection_timeout_sec"])


async def led_connect_loop():
    global cleanup_scheduled
    if not cleanup_scheduled:
        asyncio.create_task(schedule_cleanup())
        cleanup_scheduled = True

    for _ in range(int(config["connection_retries"])):
        try:
            await led_connect()
            break
        except Exception as e:
            print(
                f"{timestamp()} Could not connect to BLE LED. Is there an existing or old connection? Try restarting bluetooth. Error: {e}",
                file=sys.stderr)


async def await_connection():
    for _ in range(3):
        try:
            await client.connect(timeout=config["connection_timeout_sec"])
            break
        except Exception as e:
            print(f"{timestamp()} BLE Device Service unavailable ({e}). Trying again.", file=sys.stderr)


async def led_connect() -> None:
    print(f"{timestamp()} Connecting to BLE LED strip.")
    device = await discover_device()
    print(f"{timestamp()} Device discovered.")
    global client
    client = BleakClient(device)
    await await_connection()

    if client.is_connected:
        print(f"{timestamp()} Connected!")
    else:
        raise ConnectionError(
            f"{timestamp()} BLE Connection to {config["led_mac"]} failed after several retries.")


def timestamp():
    return datetime.datetime.now().strftime("%H:%M:%S")


def sighandler(signum, frame) -> None:
    print(f"{timestamp()} Exiting.")
    signal_received.set()


async def schedule_cleanup() -> None:
    signal.signal(signal.SIGINT, sighandler)  # Ctrl+C
    signal.signal(signal.SIGTERM, sighandler)  # Termination signal
    signal.signal(signal.SIGBREAK, sighandler)  # Ctrl+Break
    await signal_received.wait()
    print(f"{timestamp()} Cleaning up.")
    global client
    await send_command(power_command(turnOn=False))
    await client.disconnect()
