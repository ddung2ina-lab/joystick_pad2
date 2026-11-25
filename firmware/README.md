# Joystick Pad 2 firmware

[Download JoystickPad2.uf2](https://github.com/ddung2ina-lab/joystick_pad2/releases/download/v1.0.0/JoystickPad2.uf2).

The compiled UF2 is distributed through **GitHub Releases**, not tracked in the source repository. Mechanical print files are distributed on **MakerWorld**.

- USB HID gamepad; product name **Handpad 8Key L3**.
- Eight front switches, one stick-click input, and two analog axes.
- The four physical left/right button pairs have been exchanged to match the existing wiring. See the root README for the front-view layout.
- Stick SW remains **GPIO9 → L3**. The bottom row is **GPIO10 → Select**, **GPIO8 → Start**.
- The known working **W25Q32** boot code and analog-axis logic are retained.
- L2/R2 are digital buttons, not analog trigger axes.

The compiled button table was checked in both the ELF and the distributed UF2. All 256 boot-code bytes match the working W25Q32 firmware. The current left/right correction has not yet been tested on the physical controller.

## Flashing

Hold **BOOT** while connecting the board with a USB data cable. Release it when **RPI-RP2** appears, then copy `JoystickPad2.uf2` to that drive. The board restarts automatically. Reconnect normally without BOOT and leave the stick centred during start-up.

## Editable source

- [Arduino sketch](Handpad8/Handpad8.ino)
- [GPIO and HID mapping](mapping.json)
- [Build verification report](build_report.json)
- [UF2 path sanitizer](make_public_uf2.py)

The `{GPIO, HID usage, ...}` entries in `buttons[]` define the input assignments. Update `mapping.json` when changing them; the build script verifies that the compiled table matches it.

## Rebuilding

The local toolchain uses Arduino-Pico **6.3.2**, Generic RP2040, 2 MB flash allocation, and Adafruit TinyUSB. This board requires `boot2_W25Q32JVxQ_4_padded_checksum`; generic SPI boot code did not enumerate correctly on the tested board. Other flash chips may require a different boot2 selection.

`--toolchain-root` points to a folder containing `arduino-cli.exe` and the installed `data/packages/rp2040/hardware/rp2040/6.3.2` package:

```powershell
python firmware/build.py --toolchain-root C:/path/to/handpad-arduino-build
```

The UF2 and its checksum are written to `.local/release/`. The script verifies UF2 blocks, the emitted button table, and the W25Q32 boot code, and removes absolute diagnostic build paths. It does not flash the board. A rebuild may have a different checksum; the root [SHA256SUMS.txt](../SHA256SUMS.txt) identifies the published release asset.
