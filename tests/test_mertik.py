"""Tests for the Mertik hardware communication layer."""

from unittest.mock import MagicMock, patch, call

import pytest
import socket

from custom_components.mertik.mertik import (
    Mertik,
    COMMAND_PREFIX as send_command_prefix,
)
from tests.conftest import _build_status_bytes

GUARD = "0080"  # guard flame (pilot) bit


class TestMertikInit:
    """Test Mertik class initialization."""

    def test_connects_to_correct_host_and_port(self, mock_socket):
        device = Mertik("192.168.1.50")
        mock_socket.create_connection.assert_called_with(("192.168.1.50", 2000), timeout=3)

    def test_closes_connection_after_command(self, mock_socket):
        device = Mertik("192.168.1.50")
        mock_socket.__exit__.assert_called()

    def test_calls_refresh_on_init(self, mock_socket):
        device = Mertik("192.168.1.50")
        refresh_cmd = bytearray.fromhex(send_command_prefix + "303303")
        mock_socket.sendall.assert_called_with(refresh_cmd)


class TestStatusParsing:
    """Test __processStatus parsing of status responses."""

    def test_fireplace_off_when_flame_height_low(self, mock_socket):
        """Flame height <= 0x7B means fireplace is off."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x00)
        device = Mertik("192.168.1.100")
        assert device.is_on is False
        assert device.get_flame_height() == 0

    def test_fireplace_on_when_flame_height_high(self, mock_socket):
        """Lowest manual step 0x80=128 with guard flame -> on, height=1."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x80, status_bits=GUARD)
        device = Mertik("192.168.1.100")
        assert device.is_on is True
        assert device.get_flame_height() == 1

    def test_flame_height_mid_range(self, mock_socket):
        """0xC0=192 -> nearest manual step is 0xC5 -> 7."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0xC0, status_bits=GUARD)
        device = Mertik("192.168.1.100")
        assert device.is_on is True
        assert device.get_flame_height() == 7

    def test_flame_height_max(self, mock_socket):
        """0xFF=255 is the highest of the 12 manual steps."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0xFF, status_bits=GUARD)
        device = Mertik("192.168.1.100")
        assert device.is_on is True
        assert device.get_flame_height() == 12

    def test_flame_height_boundary(self, mock_socket):
        """0x7B=123 is the boundary - still off."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x7B)
        device = Mertik("192.168.1.100")
        assert device.is_on is False

    def test_ambient_temperature(self, mock_socket):
        """0xE6=230 -> 230/10 = 23.0 C."""
        mock_socket.recv.return_value = _build_status_bytes(ambient_temp=0xE6)
        device = Mertik("192.168.1.100")
        assert device.ambient_temperature == 23.0

    def test_ambient_temperature_different_value(self, mock_socket):
        """0xC8=200 -> 200/10 = 20.0 C."""
        mock_socket.recv.return_value = _build_status_bytes(ambient_temp=0xC8)
        device = Mertik("192.168.1.100")
        assert device.ambient_temperature == 20.0

    def test_light_brightness_max(self, mock_socket):
        """light_level 0xFB=251 with light on -> round(((251-100)/151)*255) = 255."""
        # Use status_bits with bit 13 set (light_on) — need 16-bit value for stable indexing
        # Bit 13 in 16-bit: 2^(15-13) = 0x0004, plus 0x8000 base for 16-bit length
        mock_socket.recv.return_value = _build_status_bytes(
            light_level=0xFB, status_bits="8004"
        )
        device = Mertik("192.168.1.100")
        assert device.light_brightness == 255

    def test_light_brightness_minimum(self, mock_socket):
        """light_level 0x64=100 -> round(((100-100)/151)*255) = 0."""
        mock_socket.recv.return_value = _build_status_bytes(
            light_level=0x64, status_bits="8004"
        )
        device = Mertik("192.168.1.100")
        assert device.light_brightness == 0

    def test_light_off_brightness_zero(self, mock_socket):
        """When light is off, brightness is forced to 0."""
        mock_socket.recv.return_value = _build_status_bytes(
            light_level=0xFB, status_bits="0000"
        )
        device = Mertik("192.168.1.100")
        assert device.light_brightness == 0

    def test_status_bits_shutting_down(self, mock_socket):
        """Bit 7 -> shutting_down. In 16-bit: 2^(15-7)=0x0100, base 0x8000."""
        mock_socket.recv.return_value = _build_status_bytes(status_bits="8100")
        device = Mertik("192.168.1.100")
        assert device.is_shutting_down is True

    def test_status_bits_igniting(self, mock_socket):
        """Bit 11 -> igniting. In 16-bit: 2^(15-11)=0x0010, base 0x8000."""
        mock_socket.recv.return_value = _build_status_bytes(status_bits="8010")
        device = Mertik("192.168.1.100")
        assert device.is_igniting is True

    def test_status_bits_aux_on(self, mock_socket):
        """Bit 12 -> aux_on. In 16-bit: 2^(15-12)=0x0008, base 0x8000."""
        mock_socket.recv.return_value = _build_status_bytes(status_bits="8008")
        device = Mertik("192.168.1.100")
        assert device.is_aux_on is True

    def test_status_bits_light_on(self, mock_socket):
        """Bit 13 -> light_on. In 16-bit: 2^(15-13)=0x0004, base 0x8000."""
        mock_socket.recv.return_value = _build_status_bytes(status_bits="8004")
        device = Mertik("192.168.1.100")
        assert device.is_light_on is True

    def test_status_bits_all_clear(self, mock_socket):
        """All status bits clear -> all flags False."""
        mock_socket.recv.return_value = _build_status_bytes(status_bits="0000")
        device = Mertik("192.168.1.100")
        assert device.is_shutting_down is False
        assert device.is_igniting is False
        assert device.is_aux_on is False
        assert device.is_light_on is False

    def test_second_status_prefix_accepted(self, mock_socket):
        """The alternate prefix '030300000003' should also be parsed."""
        raw = _build_status_bytes(flame_height=0x80, status_bits=GUARD)
        mock_socket.recv.return_value = raw.replace(b"303030300003", b"030300000003")
        device = Mertik("192.168.1.100")
        assert device.is_on is True
        assert device.ambient_temperature == 23.0


class TestCommands:
    """Test command sending."""

    def test_standby_sends_correct_command(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.standBy()
        expected = bytearray.fromhex(send_command_prefix + "3136303003")
        mock_socket.sendall.assert_called_with(expected)

    def test_ignite_sends_correct_command(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.ignite_fireplace()
        expected = bytearray.fromhex(send_command_prefix + "314103")
        mock_socket.sendall.assert_called_with(expected)

    def test_aux_on_sends_correct_command(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.aux_on()
        expected = bytearray.fromhex(send_command_prefix + "32303031030a")
        mock_socket.sendall.assert_called_with(expected)

    def test_aux_off_sends_correct_command(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.aux_off()
        expected = bytearray.fromhex(send_command_prefix + "32303030030a")
        mock_socket.sendall.assert_called_with(expected)

    def test_light_on_sends_correct_command(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.light_on()
        expected = bytearray.fromhex(send_command_prefix + "3330303103")
        mock_socket.sendall.assert_called_with(expected)

    def test_light_off_sends_correct_command(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.light_off()
        expected = bytearray.fromhex(send_command_prefix + "3330303003")
        mock_socket.sendall.assert_called_with(expected)

    def test_refresh_status_sends_correct_command(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.refresh_status()
        expected = bytearray.fromhex(send_command_prefix + "303303")
        mock_socket.sendall.assert_called_with(expected)

    def test_guard_flame_off_sends_correct_command(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.guard_flame_off()
        expected = bytearray.fromhex(send_command_prefix + "313003")
        mock_socket.sendall.assert_called_with(expected)

    def test_set_eco_sends_correct_command(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.set_eco()
        expected = bytearray.fromhex(send_command_prefix + "4233303103")
        mock_socket.sendall.assert_called_with(expected)

    def test_set_manual_sends_correct_command(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.set_manual()
        expected = bytearray.fromhex(send_command_prefix + "423003")
        mock_socket.sendall.assert_called_with(expected)


class TestFlameHeight:
    """Test flame height commands."""

    def test_set_flame_height_step_1(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.set_flame_height(1)
        expected = bytearray.fromhex(send_command_prefix + "3136383003")
        assert mock_socket.sendall.call_args_list[0] == call(expected)

    def test_set_flame_height_step_12(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.set_flame_height(12)
        expected = bytearray.fromhex(send_command_prefix + "3136464603")
        assert mock_socket.sendall.call_args_list[0] == call(expected)

    def test_set_flame_height_step_6(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.set_flame_height(6)
        expected = bytearray.fromhex(send_command_prefix + "3136423903")
        assert mock_socket.sendall.call_args_list[0] == call(expected)

    def test_set_flame_height_calls_refresh(self, mertik_device, mock_socket):
        mock_socket.sendall.reset_mock()
        mertik_device.set_flame_height(1)
        refresh_cmd = bytearray.fromhex(send_command_prefix + "303303")
        assert mock_socket.sendall.call_args_list[1] == call(refresh_cmd)


class TestLightBrightness:
    """Test light brightness commands."""

    def test_brightness_max(self, mertik_device, mock_socket):
        """Brightness 255 -> device code 4642."""
        mock_socket.sendall.reset_mock()
        mertik_device.set_light_brightness(255)
        expected = bytearray.fromhex(send_command_prefix + "33304645464203")
        mock_socket.sendall.assert_called_with(expected)

    def test_brightness_min(self, mertik_device, mock_socket):
        """Brightness 1 -> device code 3633."""
        mock_socket.sendall.reset_mock()
        mertik_device.set_light_brightness(1)
        expected = bytearray.fromhex(send_command_prefix + "33304645363303")
        mock_socket.sendall.assert_called_with(expected)

    def test_brightness_mid(self, mertik_device, mock_socket):
        """brightness=128 -> normalized=50 -> l=40 -> l+=1=41 -> code '4141'."""
        mock_socket.sendall.reset_mock()
        mertik_device.set_light_brightness(128)
        expected = bytearray.fromhex(send_command_prefix + "33304645414103")
        mock_socket.sendall.assert_called_with(expected)

    def test_brightness_skip_40(self, mertik_device, mock_socket):
        """When l reaches 40, it skips to 41 (the skip-40 quirk)."""
        # brightness where normalized=50 -> l=36+round(4.0)=40 -> 40>=40 -> l=41
        mock_socket.sendall.reset_mock()
        mertik_device.set_light_brightness(128)
        cmd_bytes = mock_socket.sendall.call_args[0][0]
        cmd_hex = cmd_bytes.hex()
        # The device code is after "33304645" prefix, extract it
        payload = cmd_hex[len(send_command_prefix):]
        # payload = "33304645XXYY03", device_code = payload[8:12]
        device_code = payload[8:12]
        assert device_code == "4141"  # 41 (skipped 40)

    def test_brightness_just_below_skip(self, mertik_device, mock_socket):
        """Brightness where l=39 (below skip threshold)."""
        # normalized = (b-1)/254*100, l = 36 + round(normalized/100*8)
        # l=39 -> round(normalized/100*8)=3 -> normalized=37.5 -> b=1+37.5*254/100=96.25
        # b=96: normalized=(95/254)*100=37.40, l=36+round(2.99)=36+3=39
        mock_socket.sendall.reset_mock()
        mertik_device.set_light_brightness(96)
        cmd_bytes = mock_socket.sendall.call_args[0][0]
        payload = cmd_bytes.hex()[len(send_command_prefix):]
        device_code = payload[8:12]
        assert device_code == "3939"  # 39 (no skip applied)

    def test_brightness_near_max(self, mertik_device, mock_socket):
        """Brightness 254 (just below max)."""
        # normalized=(253/254)*100=99.6, l=36+round(7.97)=36+8=44, >=40 so l=45
        mock_socket.sendall.reset_mock()
        mertik_device.set_light_brightness(254)
        cmd_bytes = mock_socket.sendall.call_args[0][0]
        payload = cmd_bytes.hex()[len(send_command_prefix):]
        device_code = payload[8:12]
        assert device_code == "4545"  # 45

    def test_brightness_low(self, mertik_device, mock_socket):
        """Brightness 2 -> very low normalized value."""
        # normalized=(1/254)*100=0.394, l=36+round(0.031)=36+0=36
        mock_socket.sendall.reset_mock()
        mertik_device.set_light_brightness(2)
        cmd_bytes = mock_socket.sendall.call_args[0][0]
        payload = cmd_bytes.hex()[len(send_command_prefix):]
        device_code = payload[8:12]
        assert device_code == "3636"  # 36 (no skip)


class TestConnectionHandling:
    """Each command uses its own short-lived connection."""

    def test_new_connection_per_command(self, mock_socket):
        device = Mertik("192.168.1.100")
        device.refresh_status()
        device.aux_on()
        assert mock_socket.create_connection.call_count == 3

    def test_connection_error_propagates(self, mock_socket):
        device = Mertik("192.168.1.100")
        mock_socket.create_connection.side_effect = OSError("refused")
        with pytest.raises(OSError):
            device.refresh_status()

    def test_frame_split_across_reads(self, mock_socket):
        raw = _build_status_bytes(flame_height=0xFF, status_bits=GUARD)
        mock_socket.recv.side_effect = [raw[:10], raw[10:]]
        device = Mertik("192.168.1.100")
        assert device.get_flame_height() == 12

    def test_newest_of_multiple_frames_wins(self, mock_socket):
        old = _build_status_bytes(flame_height=0x80, status_bits=GUARD)
        new = _build_status_bytes(flame_height=0xFF, status_bits=GUARD)
        mock_socket.recv.return_value = old + new
        device = Mertik("192.168.1.100")
        assert device.get_flame_height() == 12

    def test_garbage_before_frame_ignored(self, mock_socket):
        frame = _build_status_bytes(flame_height=0x80, status_bits=GUARD)
        mock_socket.recv.return_value = b"\x03junk" + frame
        device = Mertik("192.168.1.100")
        assert device.get_flame_height() == 1


class TestHelperMethods:
    """Test hex2bin and fromBitStatus helpers."""

    def test_hex_to_bin(self, mertik_device):
        assert mertik_device._hex_to_bin("FF") == "11111111"
        assert mertik_device._hex_to_bin("00") == "00000000"
        assert mertik_device._hex_to_bin("80") == "10000000"
        assert mertik_device._hex_to_bin("01") == "00000001"

    def test_bit_at(self, mertik_device):
        assert mertik_device._bit_at("FF", 0) is True
        assert mertik_device._bit_at("FF", 7) is True
        assert mertik_device._bit_at("00", 0) is False
        assert mertik_device._bit_at("80", 0) is True
        assert mertik_device._bit_at("80", 1) is False


class TestNonStatusResponses:
    """A missing status frame is an error and leaves state untouched."""

    def test_non_matching_prefix_raises(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x00)
        device = Mertik("192.168.1.100")

        mock_socket.recv.return_value = b"\x02XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX\x03"
        with pytest.raises(ConnectionError):
            device.refresh_status()
        assert device.is_on is False
        assert device.get_flame_height() == 0

    def test_connection_closed_without_frame_raises(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes()
        device = Mertik("192.168.1.100")

        mock_socket.recv.return_value = b""
        with pytest.raises(ConnectionError):
            device.refresh_status()

    def test_state_preserved_across_non_status(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0xC0, status_bits=GUARD)
        device = Mertik("192.168.1.100")
        assert device.get_flame_height() == 7

        mock_socket.recv.return_value = b"\x02ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ\x03"
        with pytest.raises(ConnectionError):
            device.refresh_status()
        assert device.is_on is True
        assert device.get_flame_height() == 7


class TestAllFlameHeightSteps:
    """Test every flame height step sends the correct hex code."""

    EXPECTED_STEPS = [
        (1, "3830"), (2, "3842"), (3, "3937"), (4, "4132"),
        (5, "4145"), (6, "4239"), (7, "4335"), (8, "4430"),
        (9, "4443"), (10, "4537"), (11, "4633"), (12, "4646"),
    ]

    @pytest.mark.parametrize("step,hex_code", EXPECTED_STEPS)
    def test_flame_step(self, mertik_device, mock_socket, step, hex_code):
        mock_socket.sendall.reset_mock()
        mertik_device.set_flame_height(step)
        expected = bytearray.fromhex(send_command_prefix + "3136" + hex_code + "03")
        assert mock_socket.sendall.call_args_list[0] == call(expected)


class TestBrightnessEdgeCases:
    """Test light brightness edge cases for safe refactoring."""

    def test_light_level_below_100_clamps_to_zero(self, mock_socket):
        """Light level below 100 with light on should clamp brightness to 0."""
        # 0x50 = 80, brightness = round(((80-100)/151)*255) = -34, clamped to 0
        mock_socket.recv.return_value = _build_status_bytes(
            light_level=0x50, status_bits="8004"  # light on
        )
        device = Mertik("192.168.1.100")
        assert device.light_brightness == 0

    def test_light_level_mid_range(self, mock_socket):
        """Light level in mid range with light on."""
        # 0xAF = 175, brightness = round(((175-100)/151)*255) = round(126.6) = 127
        mock_socket.recv.return_value = _build_status_bytes(
            light_level=0xAF, status_bits="8004"
        )
        device = Mertik("192.168.1.100")
        assert device.light_brightness == 127


class TestGuardFlame:
    """Test the guard flame internal attribute."""

    def test_guard_flame_on(self, mock_socket):
        """Bit 8 -> _guard_flame_on. In 16-bit: 2^(15-8)=0x0080, base 0x8000."""
        mock_socket.recv.return_value = _build_status_bytes(status_bits="8080")
        device = Mertik("192.168.1.100")
        assert device._guard_flame_on is True

    def test_guard_flame_off(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(status_bits="8000")
        device = Mertik("192.168.1.100")
        assert device._guard_flame_on is False


class TestStateTransitions:
    """Test that state updates correctly across multiple status responses."""

    def test_off_to_on(self, mock_socket):
        """State should transition from off to on."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x00)
        device = Mertik("192.168.1.100")
        assert device.is_on is False

        mock_socket.recv.return_value = _build_status_bytes(flame_height=0xC0, status_bits=GUARD)
        device.refresh_status()
        assert device.is_on is True
        assert device.get_flame_height() == 7

    def test_on_to_off(self, mock_socket):
        """State should transition from on to off."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0xC0, status_bits=GUARD)
        device = Mertik("192.168.1.100")
        assert device.is_on is True

        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x00)
        device.refresh_status()
        assert device.is_on is False
        assert device.get_flame_height() == 0

    def test_temperature_updates(self, mock_socket):
        """Temperature should update on each status response."""
        mock_socket.recv.return_value = _build_status_bytes(ambient_temp=0xC8)
        device = Mertik("192.168.1.100")
        assert device.ambient_temperature == 20.0

        mock_socket.recv.return_value = _build_status_bytes(ambient_temp=0xFA)
        device.refresh_status()
        assert device.ambient_temperature == 25.0

    def test_all_properties_update_together(self, mock_socket):
        """All parsed properties should update from a single status response."""
        mock_socket.recv.return_value = _build_status_bytes(
            flame_height=0xC0,
            status_bits="801C",  # igniting + aux + light on
            light_level=0xFB,
            ambient_temp=0xE6,
        )
        device = Mertik("192.168.1.100")

        assert device.is_on is True
        assert device.get_flame_height() == 7
        assert device.is_igniting is True
        assert device.is_aux_on is True
        assert device.is_light_on is True
        assert device.light_brightness == 255
        assert device.ambient_temperature == 23.0

        # Now update everything at once
        mock_socket.recv.return_value = _build_status_bytes(
            flame_height=0x00,
            status_bits="8000",  # all off
            light_level=0x64,
            ambient_temp=0xC8,
        )
        device.refresh_status()

        assert device.is_on is False
        assert device.get_flame_height() == 0
        assert device.is_igniting is False
        assert device.is_aux_on is False
        assert device.is_light_on is False
        assert device.light_brightness == 0
        assert device.ambient_temperature == 20.0


class TestFireplaceState:
    """Off / standby / igniting / on / shutting down, as the MyFire app shows them."""

    def test_off_without_guard_flame(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x00, status_bits="0000")
        device = Mertik("192.168.1.100")
        assert device.state == "off"
        assert device.is_on is False

    @pytest.mark.parametrize("raw", [0x00, 0x20, 0x40])
    def test_standby_is_pilot_only(self, mock_socket, raw):
        """Measured on a B6R-W2BE-0: standby reports burner 0-32 with the guard bit still set."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=raw, status_bits="828A")
        device = Mertik("192.168.1.100")
        assert device.state == "standby"
        assert device.is_on is False
        assert device.get_flame_height() == 0
        assert device.is_aux_on is True

    def test_low_fire_below_lowest_manual_step_is_on(self, mock_socket):
        """The handset's flame wave burns at 0x69, below the lowest manual step 0x80."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x69, status_bits="828A")
        device = Mertik("192.168.1.100")
        assert device.state == "on"
        assert device.is_on is True
        assert device.get_flame_height() == 1

    def test_on_at_lowest_step(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x80, status_bits="828A")
        device = Mertik("192.168.1.100")
        assert device.state == "on"
        assert device.is_on is True

    def test_igniting(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x00, status_bits="0010")
        device = Mertik("192.168.1.100")
        assert device.state == "igniting"
        assert device.is_on is True

    def test_shutting_down(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x80, status_bits="0180")
        device = Mertik("192.168.1.100")
        assert device.state == "shutting_down"
        assert device.is_on is False

    def test_eco_low_phase_counts_as_on(self, mock_socket):
        """Eco modulates the burner below the lowest manual step while running."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x69, status_bits="0080", mode="2")
        device = Mertik("192.168.1.100")
        assert device.state == "on"

    def test_status_bits_use_full_16_bits(self, mock_socket):
        """A status word without the top bit set must not shift the bit indices."""
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x80, status_bits="0084")
        device = Mertik("192.168.1.100")
        assert device._guard_flame_on is True
        assert device.is_light_on is True
        assert device.is_aux_on is False


class TestModeAndTemperatures:
    """Operating mode and the 16-bit temperature fields."""

    @pytest.mark.parametrize("char,mode", [("0", "manual"), ("1", "temperature"), ("2", "eco"), ("3", "manual")])
    def test_mode_parsing(self, mock_socket, char, mode):
        mock_socket.recv.return_value = _build_status_bytes(mode=char)
        device = Mertik("192.168.1.100")
        assert device.mode == mode

    @pytest.mark.parametrize("mode,payload", [("manual", "423003"), ("eco", "4233303103"), ("temperature", "4232303103")])
    def test_set_mode_sends_command(self, mertik_device, mock_socket, mode, payload):
        mertik_device.set_mode(mode)
        mock_socket.sendall.assert_called_with(bytearray.fromhex(send_command_prefix + payload))

    def test_temperatures_above_25_5(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(ambient_temp=0x0105, target_temp=0x00C8)
        device = Mertik("192.168.1.100")
        assert device.ambient_temperature == 26.1
        assert device.target_temperature == 20.0

    def test_real_frame_from_device(self, mock_socket):
        """Verbatim status frame captured from a Bellfires B6R-W2BE-0 in its flame wave's low phase."""
        frame = "0303000000034069828A0000000000E100C84B65756B656E" + "F" * 30 + "0" * 24 + "044008"
        mock_socket.recv.return_value = ("\x02" + frame + "\x03").encode("ascii")
        device = Mertik("192.168.1.100")
        assert device.state == "on"
        assert device.get_flame_height() == 1
        assert device.mode == "manual"
        assert device.ambient_temperature == 22.5
        assert device.target_temperature == 20.0


class TestDiagnostics:
    """Raw status fields are exposed for diagnosing other devices."""

    def test_diagnostics(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x69, status_bits="828A", mode="0")
        device = Mertik("192.168.1.100")
        assert device.diagnostics == {
            "raw_burner_output": 0x69,
            "raw_status_bits": "828A",
            "raw_mode": "0",
            "raw_end": "C8",
        }


class TestReceiverLink:
    """Frames sent while the module has lost its receiver link are not trusted."""

    def test_real_ignition_sequence(self, mock_socket):
        """Status words captured on a B6R-W2BE-0 while relighting from fully off."""
        sequence = [
            (0x00, "820A", "off"),
            (0x00, "821A", "igniting"),
            (0x00, "021A", None),  # receiver link lost
            (0xFF, "828A", "on"),
            (0xFF, "028A", None),
            (0xFF, "008A", None),
            (0x00, "820A", "off"),  # pilot did not hold, retry follows
        ]
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x00, status_bits="820A")
        device = Mertik("192.168.1.100")
        for raw, bits, expected in sequence:
            mock_socket.recv.return_value = _build_status_bytes(flame_height=raw, status_bits=bits)
            device.refresh_status()
            assert device.state == expected, bits

    def test_link_loss_keeps_last_reliable_values(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0xFF, status_bits="828A")
        device = Mertik("192.168.1.100")
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x00, status_bits="008A")
        device.refresh_status()
        assert device.state is None
        assert device.is_on is True
        assert device.get_flame_height() == 12
        assert device.diagnostics["raw_status_bits"] == "008A"

    def test_devices_without_link_bit_are_unaffected(self, mock_socket):
        mock_socket.recv.return_value = _build_status_bytes(flame_height=0x80, status_bits="0080")
        device = Mertik("192.168.1.100")
        assert device.state == "on"
