import unittest

from tailscale_host import (
    discover_gui_env,
    find_deskflow_core,
    get_displays,
    get_os_info,
    get_tailscale_info,
)


class TailscaleHostTests(unittest.TestCase):
    def test_os_info_shape(self) -> None:
        info = get_os_info()
        self.assertIn(info["os"], ("windows", "linux", "macos"))
        self.assertTrue(bool(info["os_detail"]))

    def test_displays_bounds_sanity(self) -> None:
        disp = get_displays()
        self.assertGreater(disp["width"], 0)
        self.assertGreater(disp["height"], 0)
        self.assertGreaterEqual(len(disp["monitors"]), 1)
        m0 = disp["monitors"][0]
        self.assertGreater(m0["width"], 0)
        self.assertGreater(m0["height"], 0)

    def test_tailscale_info_shape_and_env(self) -> None:
        ts = get_tailscale_info()
        self.assertIn("tailscale_ok", ts)
        self.assertIn("ip", ts)
        self.assertIn("hostname", ts)
        self.assertIn("dns_name", ts)
        self.assertIsInstance(discover_gui_env(), dict)
        core = find_deskflow_core()
        self.assertTrue(core is None or isinstance(core, str))


if __name__ == "__main__":
    unittest.main()
