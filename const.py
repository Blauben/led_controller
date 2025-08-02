config_template = """led_mac: "" # The ble mac address for the LED strip
gatt_char_uuid: "0000fff3-0000-1000-8000-00805f9b34fb" # The attr field for transmitting ble commands
connection_timeout_sec: 30 # The timeout for looking for the LED strip with address led_mac
connection_retries: 50 # How often to repeat connections if the device has been successfully discovered before
"""

help_page = """\nInstructions:
Random color change - Press ENTER
Turn off LED - Type "off" to turn off LED.
Turn on LED - Type "on" to turn on the LED.
Set off time in minutes - Type "s <minutes>"
Set brightness - Type "b <brightness>" with brightness between 0 and 1
Help Page - Type "help" to show this menu.
To quit this program press CTRL + C (turns off LED) or type "q" to exit without doing anything.
"""