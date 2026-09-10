from freebox_pop_remote.utils import decode_mdns_property, safe_host_dir


def test_decode_mdns_property():
    assert decode_mdns_property(None) == ""
    assert decode_mdns_property("Pop") == "Pop"
    assert decode_mdns_property(b"Player Pop") == "Player Pop"
    assert "\ufffd" in decode_mdns_property(b"bad\xffname")


def test_safe_host_dir():
    assert safe_host_dir("192.168.1.42") == "192.168.1.42"
    assert safe_host_dir("fe80::1%wlan0") == "fe80_1_wlan0"
    assert safe_host_dir("living room") == "living_room"
