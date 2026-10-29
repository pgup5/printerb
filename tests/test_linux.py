"""Linux font rendering and serial integration checks without a printer."""
import errno
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from printerb_core import b1_label_printer as b1


class LinuxTests(unittest.TestCase):
    def test_linux_serial_port_selection(self):
        ports = [SimpleNamespace(device="/dev/ttyS0", description="Built-in",
                                 manufacturer=None, product=None, hwid=""),
                 SimpleNamespace(device="/dev/ttyUSB0", description="USB Serial",
                                 manufacturer="wch", product=None, hwid="")]
        with patch.object(b1, "available_serial_ports", return_value=ports):
            self.assertEqual(b1.find_niimbot_port(), "/dev/ttyUSB0")
            self.assertEqual(b1.find_niimbot_port("/dev/ttyUSB0"), "/dev/ttyUSB0")

    def test_permission_error_explains_linux_group(self):
        with patch.object(b1.sys, "platform", "linux"), patch.object(
            b1.serial, "Serial", side_effect=PermissionError(errno.EACCES, "Permission denied")
        ):
            with self.assertRaisesRegex(b1.PrinterCommunicationError, "dialout"):
                b1._B1Client("/dev/ttyUSB0")

    def test_noto_collection_uses_traditional_chinese_face(self):
        with patch.object(Path, "is_file", return_value=True), patch.object(
            b1.ImageFont, "truetype"
        ) as load:
            b1._load_chinese_font(24)
            self.assertEqual(load.call_args.kwargs["index"], 3)
