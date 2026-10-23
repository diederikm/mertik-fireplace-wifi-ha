"""Mertik Maxitrol WiFi fireplace controller."""

import logging
import socket
import threading
import time

_LOGGER = logging.getLogger(__name__)

# Protocol framing
STX = "\x02"
ETX = "\x03"
COMMAND_PREFIX = "0233303330333033303830"
STATUS_PREFIXES = ("303030300003", "030300000003")
TCP_PORT = 2000
SOCKET_TIMEOUT = 3
RECV_BUFFER = 1024

# Command payloads (appended to COMMAND_PREFIX)
CMD_STANDBY = "3136303003"
CMD_IGNITE = "314103"
CMD_GUARD_FLAME_OFF = "313003"
CMD_REFRESH_STATUS = "303303"
CMD_AUX_ON = "32303031030a"
CMD_AUX_OFF = "32303030030a"
CMD_LIGHT_ON = "3330303103"
CMD_LIGHT_OFF = "3330303003"
CMD_SET_ECO = "4233303103"
CMD_SET_MANUAL = "423003"
CMD_SET_TEMPERATURE = "4232303103"
CMD_FLAME_PREFIX = "3136"
CMD_FLAME_SUFFIX = "03"
CMD_BRIGHTNESS_PREFIX = "33304645"
CMD_BRIGHTNESS_SUFFIX = "03"

# Brightness device codes for min/max
BRIGHTNESS_CODE_MAX = "4642"
BRIGHTNESS_CODE_MIN = "3633"

# Flame height hex codes for steps 1-12 (ASCII hex of raw values 0x80..0xFF)
FLAME_HEIGHT_STEPS = [
    "3830", "3842", "3937", "4132", "4145", "4239",
    "4335", "4430", "4443", "4537", "4633", "4646",
]
FLAME_HEIGHT_RAW = [int(bytes.fromhex(code).decode("ascii"), 16) for code in FLAME_HEIGHT_STEPS]

# Status response field offsets (indices into the frame after stripping STX)
#   [0:12]   prefix
#   [12:14]  constant
#   [14:16]  burner output (raw 0x00-0xFF, manual steps are 0x80-0xFF)
#   [16:20]  status bits (16 bits, MSB first)
#   [20:22]  light level
#   [22:24]  fan speed
#   [24:25]  operating mode
#   [28:32]  current temperature (x10)
#   [32:36]  target temperature (x10)
STATUS_FLAME_HEIGHT = slice(14, 16)
STATUS_BITS = slice(16, 20)
STATUS_LIGHT_LEVEL = slice(20, 22)
STATUS_MODE = slice(24, 25)
STATUS_AMBIENT_TEMP = slice(28, 32)
STATUS_TARGET_TEMP = slice(32, 36)

# Status bit indices (within the 16-bit binary representation of the status word)
BIT_SHUTTING_DOWN = 7
BIT_GUARD_FLAME = 8
BIT_IGNITING = 11
BIT_AUX_ON = 12
BIT_LIGHT_ON = 13

# Burner output at or below this means only the pilot is burning. Measured on a
# B6R-W2BE-0: standby reports 0-32, while eco's lowest phase still burns at 105,
# below the lowest manual step (0x80).
STANDBY_MAX_RAW = 64

# Light level range from the device
DEVICE_LIGHT_MIN = 100
DEVICE_LIGHT_MAX = 251

# Operating modes reported in the mode character
MODE_MANUAL = "manual"
MODE_TEMPERATURE = "temperature"
MODE_ECO = "eco"
MODE_CHARS = {"0": MODE_MANUAL, "1": MODE_TEMPERATURE, "2": MODE_ECO}

# Fireplace states
STATE_OFF = "off"
STATE_STANDBY = "standby"
STATE_IGNITING = "igniting"
STATE_ON = "on"
STATE_SHUTTING_DOWN = "shutting_down"


class Mertik:
    """Talks to the WiFi module over short-lived TCP connections.

    The module serves a single client at a time and pushes unsolicited status
    frames on an open socket. Holding a socket open makes reads return stale,
    buffered frames and blocks other clients (such as the MyFire app), so every
    command opens its own connection and parses the newest status frame.
    """

    def __init__(self, ip):
        self.ip = ip
        self._lock = threading.Lock()
        self.on = False
        self.flameHeight = 0
        self._raw_flame = 0
        self._raw_status_bits = None
        self._raw_mode = None
        self._raw_end = None
        self._mode = MODE_MANUAL
        self._state = STATE_OFF
        self._shutting_down = False
        self._guard_flame_on = False
        self._igniting = False
        self._aux_on = False
        self._light_on = False
        self._light_brightness = 0
        self._ambient_temperature = None
        self._target_temperature = None
        self.refresh_status()

    @property
    def is_on(self) -> bool:
        return self.on

    @property
    def state(self) -> str:
        return self._state

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_aux_on(self) -> bool:
        return self._aux_on

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    @property
    def is_igniting(self) -> bool:
        return self._igniting

    @property
    def ambient_temperature(self) -> float:
        return self._ambient_temperature

    @property
    def target_temperature(self) -> float:
        return self._target_temperature

    @property
    def is_light_on(self) -> bool:
        return self._light_on

    @property
    def light_brightness(self) -> int:
        return self._light_brightness

    def standBy(self):
        self._send_command(CMD_STANDBY)

    def aux_on(self):
        self._send_command(CMD_AUX_ON)

    def aux_off(self):
        self._send_command(CMD_AUX_OFF)

    def ignite_fireplace(self):
        self._send_command(CMD_IGNITE)

    def refresh_status(self):
        self._send_command(CMD_REFRESH_STATUS)

    def guard_flame_off(self):
        self._send_command(CMD_GUARD_FLAME_OFF)

    def light_on(self):
        self._send_command(CMD_LIGHT_ON)

    def light_off(self):
        self._send_command(CMD_LIGHT_OFF)

    def set_light_brightness(self, brightness) -> None:
        normalized = (brightness - 1) / 254 * 100

        if normalized == 100:
            device_code = BRIGHTNESS_CODE_MAX
        elif normalized == 0:
            device_code = BRIGHTNESS_CODE_MIN
        else:
            level = 36 + round(normalized / 100 * 8)
            if level >= 40:
                level += 1  # Device skips code 40
            device_code = f"{level:02d}{level:02d}"

        self._send_command(f"{CMD_BRIGHTNESS_PREFIX}{device_code}{CMD_BRIGHTNESS_SUFFIX}")

    def set_eco(self):
        self._send_command(CMD_SET_ECO)

    def set_manual(self):
        self._send_command(CMD_SET_MANUAL)

    def set_temperature_mode(self):
        self._send_command(CMD_SET_TEMPERATURE)

    def set_mode(self, mode) -> None:
        commands = {
            MODE_MANUAL: CMD_SET_MANUAL,
            MODE_ECO: CMD_SET_ECO,
            MODE_TEMPERATURE: CMD_SET_TEMPERATURE,
        }
        self._send_command(commands[mode])

    def get_flame_height(self) -> int:
        return self.flameHeight

    def set_flame_height(self, flame_height) -> None:
        step_code = FLAME_HEIGHT_STEPS[flame_height - 1]
        self._send_command(f"{CMD_FLAME_PREFIX}{step_code}{CMD_FLAME_SUFFIX}")
        self.refresh_status()

    def _hex_to_bin(self, hex_str):
        return format(int(hex_str, 16), "b").zfill(len(hex_str) * 4)

    def _bit_at(self, hex_str, index):
        return self._hex_to_bin(hex_str)[index : index + 1] == "1"

    def _send_command(self, msg):
        payload = bytearray.fromhex(COMMAND_PREFIX + msg)

        with self._lock:
            with socket.create_connection((self.ip, TCP_PORT), timeout=SOCKET_TIMEOUT) as client:
                client.sendall(payload)
                status = self._read_status(client)

        if status is None:
            raise ConnectionError(f"No status frame received from {self.ip}")
        self._process_status(status)

    def _read_status(self, client):
        """Read until a complete status frame arrives; return the newest one."""
        buffer = ""
        newest = None
        deadline = time.monotonic() + SOCKET_TIMEOUT

        while newest is None and time.monotonic() < deadline:
            try:
                data = client.recv(RECV_BUFFER)
            except socket.timeout:
                break
            if not data:
                break
            buffer += data.decode("ascii", errors="replace")
            frames, buffer = _split_frames(buffer)
            for frame in frames:
                if frame.startswith(STATUS_PREFIXES):
                    newest = frame

        return newest

    @property
    def diagnostics(self) -> dict:
        """Raw status fields, for diagnosing devices that report differently."""
        return {
            "raw_burner_output": self._raw_flame,
            "raw_status_bits": self._raw_status_bits,
            "raw_mode": self._raw_mode,
            "raw_end": self._raw_end,
        }

    def _process_status(self, status_str):
        raw_flame = int(status_str[STATUS_FLAME_HEIGHT], 16)
        self._raw_flame = raw_flame
        self._raw_status_bits = status_str[STATUS_BITS]
        self._raw_mode = status_str[STATUS_MODE]
        self._raw_end = status_str[-2:]

        status_bits = status_str[STATUS_BITS]
        self._shutting_down = self._bit_at(status_bits, BIT_SHUTTING_DOWN)
        self._guard_flame_on = self._bit_at(status_bits, BIT_GUARD_FLAME)
        self._igniting = self._bit_at(status_bits, BIT_IGNITING)
        self._aux_on = self._bit_at(status_bits, BIT_AUX_ON)
        self._light_on = self._bit_at(status_bits, BIT_LIGHT_ON)
        self._mode = MODE_CHARS.get(status_str[STATUS_MODE], MODE_MANUAL)

        burning = raw_flame > STANDBY_MAX_RAW
        self.flameHeight = _nearest_flame_step(raw_flame) if burning else 0

        # The guard flame bit stays set in standby as well as while burning, so
        # only the burner output tells standby apart from a (low) fire.
        if self._shutting_down:
            self._state = STATE_SHUTTING_DOWN
        elif self._igniting:
            self._state = STATE_IGNITING
        elif not self._guard_flame_on:
            self._state = STATE_OFF
        elif burning:
            self._state = STATE_ON
        else:
            self._state = STATE_STANDBY
        self.on = self._state in (STATE_ON, STATE_IGNITING)

        raw_light = int(status_str[STATUS_LIGHT_LEVEL], 16)
        self._light_brightness = round(
            ((raw_light - DEVICE_LIGHT_MIN) / (DEVICE_LIGHT_MAX - DEVICE_LIGHT_MIN)) * 255
        )
        if self._light_brightness < 0 or not self._light_on:
            self._light_brightness = 0

        self._ambient_temperature = _parse_temperature(status_str[STATUS_AMBIENT_TEMP])
        self._target_temperature = _parse_temperature(status_str[STATUS_TARGET_TEMP])


def _split_frames(buffer):
    """Split a buffer into complete STX..ETX frames and the incomplete remainder."""
    frames = []
    while True:
        start = buffer.find(STX)
        if start == -1:
            return frames, ""
        end = buffer.find(ETX, start + 1)
        if end == -1:
            return frames, buffer[start:]
        frames.append(buffer[start + 1 : end])
        buffer = buffer[end + 1 :]


def _nearest_flame_step(raw_flame):
    """Map a raw burner output to the nearest manual step (1-12)."""
    distances = [abs(raw_flame - step) for step in FLAME_HEIGHT_RAW]
    return distances.index(min(distances)) + 1


def _parse_temperature(hex_str):
    try:
        return int(hex_str, 16) / 10
    except ValueError:
        return None
