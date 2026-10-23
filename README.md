# Mertik Maxitrol Fireplace for Home Assistant

Local control of gas fireplaces with a Mertik Maxitrol WiFi module (B6R-WME, B6R-W2BE-0, B6R-WWN;
MyFire, Barbas Gas, Gazco MyFire and similar apps).

Fork of [jkfran/mertik-fireplace-wifi-ha](https://github.com/jkfran/mertik-fireplace-wifi-ha) that adds:
- a status sensor: `off`, `standby` (pilot only), `igniting`, `on`, `shutting_down`
- a mode select: `manual`, `eco`, `temperature`
- a target temperature sensor
- flame height 1-12 (was 1-13)
- no more freezing when the MyFire app is used: one short connection per poll

Protocol details: [PROTOCOL.md](PROTOCOL.md).

## Install

HACS → Custom repositories → add `https://github.com/diederikm/mertik-fireplace-wifi-ha` (Integration) →
download → restart. Coming from jkfran's version: remove that one in HACS first; entities are kept.

Then: Settings → Devices & services → Add integration → **Mertik Maxitrol**, and enter the module's IP
(use a DHCP reservation).

## Safety

This controls a gas appliance. Avoid automations that ignite it when nobody is home. Use at your own risk.
