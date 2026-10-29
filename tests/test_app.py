import unittest
from unittest.mock import patch

from main import FIELDS, LABELS, PrinterApp, render_label
from printerb_core import b1_label_printer as b1


class StandaloneTests(unittest.TestCase):
    def test_print_and_diagnostics_without_child_windows(self):
        with patch.object(b1, "available_serial_ports", return_value=[]):
            app = PrinterApp()
        app.withdraw()
        try:
            data = dict(name="王小明", number="123456", id="A123456789",
                        birthday="2020/05/20", carrier="/ABC1234")
            data.update(b1._sample_data())
            for key, value in data.items():
                if key in app.fields:
                    app.fields[key].set(value)
            app.text.insert("1.0", "收集檢體")
            with patch.object(app, "start_job", side_effect=lambda action: action()), patch.object(b1, "print_image", return_value="COM7") as printer, patch("main.tk.Toplevel") as child:
                app.print_label()
                self.assertEqual(printer.call_count, 1)
                self.assertEqual(printer.call_args.args[0].size, b1.LABEL_SIZE)
                app.events.put((True, {"battery": 90}, True))
                app.poll()
                self.assertIn('"battery": 90', app.diagnostic_output.get("1.0", "end"))
                child.assert_not_called()
        finally:
            app.destroy()

    def test_all_label_types_render_without_printer(self):
        data = {key: "" for key, _ in FIELDS}
        data.update(name="王小明", number="123456", id="A123456789",
                    birthday="2020/05/20", carrier="/ABC1234")
        data.update(b1._sample_data())
        for kind in LABELS:
            with self.subTest(kind=kind):
                image = render_label(kind, data, "收集檢體\n請冷藏")
                self.assertEqual(image.size, (384, 240))
                self.assertEqual(image.mode, "1")
                self.assertIsNotNone(image.getbbox())
                self.assertEqual(image.getextrema(), (0, 1))
        data.update(b1._sample_data_overeq3())
        self.assertEqual(render_label(LABELS[7], data, "").size, b1.LABEL_SIZE)

    def test_invalid_carrier_is_rejected(self):
        with self.assertRaises(ValueError):
            render_label(LABELS[3], {"carrier": "bad"}, "")

    def test_gui_startup_preview_and_paper_routing(self):
        with patch.object(b1, "available_serial_ports", return_value=[]):
            app = PrinterApp()
        app.withdraw()
        try:
            app.kind.set(LABELS[6])
            app.update_inputs()
            app.text.insert("1.0", "測試文字")
            self.assertEqual(app.show_preview().size, b1.LABEL_SIZE)
            app.port.set("COM7")
            for paper, feed in (("原廠紙", 0), ("副廠紙（+1 mm）", 1)):
                app.paper.set(paper)
                with patch.object(app, "start_job", side_effect=lambda action: action()), patch.object(b1, "print_image", return_value="COM7") as printer:
                    app.print_label()
                    self.assertEqual(printer.call_args.kwargs, {"port": "COM7", "density": 3, "extra_feed_mm": feed})
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
