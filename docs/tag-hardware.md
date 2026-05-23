# Tag Hardware Spec

Each ESP32 tag is built from two stacked M5Stack modules: a compute/display head and a battery base.

| Part | Product | Link |
|---|---|---|
| Compute + display + IMU | M5Stack **AtomS3R Dev Kit** | https://shop.m5stack.com/products/atoms3r-dev-kit?variant=45605332615425 |
| Battery base | M5Stack **Atomic Battery Base (200 mAh)** | https://shop.m5stack.com/products/atomic-battery-base-200mah |

## AtomS3R Dev Kit

| | |
|---|---|
| MCU | ESP32-S3-PICO-1-N8R8 — dual-core Xtensa LX7 @ 240 MHz |
| Flash / PSRAM | 8 MB / 8 MB |
| Display | 0.85" IPS LCD, 128×128, GC9107 driver |
| IMU | Bosch BMI270 6-axis (accel + gyro), I²C addr `0x68` |
| Magnetometer | Bosch BMM150 3-axis (mounted on BMI270) |
| IR | 180° FOV, ~12.46 m range |
| Wireless | 2.4 GHz Wi-Fi (BLE via ESP32-S3) |
| I/O | USB-C (OTG + Serial/JTAG), HY2.0-4P, 6× GPIO bottom pads (G5/G6/G7/G8/G38/G39) |
| Power | On-board 5 V → 3.3 V regulator |
| Size / weight | 24.0 × 24.0 × 12.9 mm / 6.8 g |
| Op. temp | 0–40 °C |

## Atomic Battery Base (200 mAh)

| | |
|---|---|
| Cell | 3.7 V, 200 mAh |
| Charger IC | LGS4056HDA linear charger, ~223 mA @ 5 V in |
| Boost | ETA9085E10, 5 V out @ up to 300 mA |
| Connector | 5-pin to Atom series host |
| Switch | DIP switch for charge/discharge mode |
| LEDs | 4-level red (battery), blue (charging), green (full) |
| Operating current | ~39.55 mA @ 4.2 V |
| Standby current | ~2.55 µA @ 4.2 V |
| Size / weight | 24.0 × 24.0 × 23.93 mm / 9.9 g |

## Stacked tag totals

| | |
|---|---|
| Footprint | 24.0 × 24.0 × ~36.8 mm |
| Weight | **~16.7 g** |
| Runtime (active) | ~5 h @ ~40 mA draw on 200 mAh |
| Runtime (deep sleep) | months — standby is 2.55 µA |

## Notes for the game

- **Liftable by the MG400 vacuum gripper.** The MG400 is rated for 500 g payload; a 16.7 g tag is ~3 % of that, leaving ample margin for vacuum pad + hose mass.
- Marker rendering uses the 128×128 IPS LCD — sufficient for AprilTag/ArUco at close camera range, but pixel count limits the usable tag dictionary and detection distance.
- BMI270 accelerometer covers the "tag was handled" detection called out in the scoring section of the README.
- Wi-Fi only (no Ethernet); all tags share the field network with the game master.
- USB-C on the AtomS3R is exposed even when stacked on the battery base — firmware reflash and charging both go through it.

## Firmware approach (PlatformIO)

Tags run a minimal ESP32-S3 firmware. Responsibilities:

1. **Join Wi-Fi** — credentials baked in at flash time or provisioned via SoftAP on first boot.
2. **Announce presence** — mDNS service (`_hhtag._tcp`) and/or periodic UDP broadcast carrying `{tag_id, ip, battery_pct, fw_version}`.
3. **Accept a control connection** from the game master (TCP or WebSocket) and act as a **remote display**:
   - `set_marker(image)` — push a framebuffer / marker ID to render on the 0.85" LCD.
   - `set_state(idle | featured | scored)` — visual state hints.
4. **Stream IMU events** back on the same connection — wake/handling/impact derived from BMI270.

Game logic lives entirely on the game master. Tags are dumb peripherals — they render what they're told and report what they feel. This means swapping the featured 10-point tag is just a `set_marker` push to a different IP.
