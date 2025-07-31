import random
import sys

from bleak import BleakClient, BleakError, BleakScanner
import yaml
import asyncio

# Load config from the yaml file
config = yaml.safe_load(open("config.yml", "r").read())


async def send_command(client: BleakClient, command: bytes) -> None:
    print(f"Sending command: {command}")
    await client.write_gatt_char(config["gatt_char_uuid"], command, response=False)


def color_command(rgb_hex: str) -> bytes:
    return bytes.fromhex(f"7e070503{rgb_hex}10ef")


def power_command(turnOn: bool) -> bytes:
    return bytes.fromhex("7e0404f00001ff00ef" if turnOn else "7e0404000000ff00ef")


async def led_connect() -> BleakClient:
    print(f"Connecting to BLE LED strip.")
    device = await BleakScanner.find_device_by_address(config["led_mac"], timeout=config["connection_timeout_sec"])
    print("Device discovered.")
    client = BleakClient(device)
    while True:
        try:
            await client.connect(timeout=config["connection_timeout_sec"])
            break
        except BleakError:
            print("Could not connect to BLE LED. Is there an existing or old connection? Try restarting bluetooth.", file=sys.stderr)

    if client.is_connected:
        print("Connected!")
        return client
    else:
        raise ConnectionError(
            f"BLE Connection to {config["led_mac"]} failed after {config["connection_timeout_sec"]} seconds.")


async def main():
    print(f"Using config param {config}")
    connection = await led_connect()
    try:
        await send_command(connection, power_command(turnOn=True))
        while True:
            await send_command(connection, color_command(rgb_hex=random.randbytes(3).hex()))
            input("Press Enter to change color...")
    finally:
        await send_command(connection, power_command(turnOn=False))
        await connection.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
