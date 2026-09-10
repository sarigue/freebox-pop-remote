from freebox_pop_remote.models import DiscoveredDevice


def test_device_label_without_model():
    device = DiscoveredDevice(name="Freebox Player", host="192.168.1.10")
    assert device.label == "Freebox Player (192.168.1.10)"


def test_device_label_with_model():
    device = DiscoveredDevice(
        name="Freebox Player",
        host="192.168.1.10",
        model="Player Pop",
    )
    assert device.label == "Freebox Player — Player Pop (192.168.1.10)"
