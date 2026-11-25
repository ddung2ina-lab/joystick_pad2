#include <Arduino.h>
#include <Adafruit_TinyUSB.h>

// RP2040 GPIO IDs. Existing joystick click pad was measured as GPIO9.
// All four physical rows corrected for mirrored left/right columns.
// GPIO9 = stick click L3; GPIO8 = Start; GPIO10 = Select.
constexpr uint8_t kVrxPin = 26;
constexpr uint8_t kVryPin = 27;
constexpr bool kSwapAxes = false;
constexpr bool kInvertX = false;
constexpr bool kInvertY = false;

struct Button {
  uint8_t pin;
  uint8_t hidUsage;
  bool rawPressed;
  bool pressed;
  uint32_t changedAt;
};

// Front view: L2/R2, X/Y, A/B, Select/Start; stick click L3.
// Explicit raw HID usages; L2/R2 are digital buttons.
Button buttons[] = {
    {3, 9, false, false, 0},  // L2, row 1, left
    {2, 10, false, false, 0},  // R2, row 1, right
    {5, 4, false, false, 0},  // X, row 2, left
    {4, 5, false, false, 0},  // Y, row 2, right
    {7, 1, false, false, 0},  // A, row 3, left
    {6, 2, false, false, 0},  // B, row 3, right
    {10, 11, false, false, 0},  // Select, row 4, left
    {8, 12, false, false, 0},  // Start, row 4, right
    {9, 14, false, false, 0},  // L3, joystick click
};
static_assert(sizeof(buttons) / sizeof(buttons[0]) == 9, "Expected 8 keys and L3");
static_assert(sizeof(Button) == 8, "Button ABI changed; update binary mapping verifier");

// Generic Desktop Game Pad: 16 button bits, then two signed 16-bit axes.
const uint8_t reportDescriptor[] = {
    0x05, 0x01,        // Usage Page (Generic Desktop)
    0x09, 0x05,        // Usage (Game Pad)
    0xA1, 0x01,        // Collection (Application)
    0x05, 0x09,        // Usage Page (Button)
    0x19, 0x01,        // Usage Minimum (Button 1)
    0x29, 0x10,        // Usage Maximum (Button 16)
    0x15, 0x00,        // Logical Minimum (0)
    0x25, 0x01,        // Logical Maximum (1)
    0x75, 0x01,        // Report Size (1 bit)
    0x95, 0x10,        // Report Count (16)
    0x81, 0x02,        // Input (Data, Variable, Absolute)
    0x05, 0x01,        // Usage Page (Generic Desktop)
    0x09, 0x30,        // Usage (X)
    0x09, 0x31,        // Usage (Y)
    0x16, 0x01, 0x80,  // Logical Minimum (-32767)
    0x26, 0xFF, 0x7F,  // Logical Maximum (32767)
    0x75, 0x10,        // Report Size (16 bits)
    0x95, 0x02,        // Report Count (2)
    0x81, 0x02,        // Input (Data, Variable, Absolute)
    0xC0,              // End Collection
};

struct GamepadReport {
  uint16_t buttons;
  int16_t x;
  int16_t y;
};
static_assert(sizeof(GamepadReport) == 6, "HID report size mismatch");

struct Axis {
  uint8_t pin;
  int32_t center;
  int32_t filtered;
  int32_t low;
  int32_t high;
};

Adafruit_USBD_HID hid;
Axis vrx{kVrxPin};
Axis vry{kVryPin};
constexpr int32_t kAdcMax = 4095;
constexpr int32_t kDeadzone = 160;
constexpr int32_t kInitialTravel = 1550;
constexpr int32_t kOutputMax = 32767;
constexpr uint32_t kDebounceMs = 6;

void setCenter(Axis &axis, int32_t average) {
  // Holding an axis against a rail at boot should not make that rail neutral.
  axis.center = (average >= 900 && average <= 3200) ? average : 2048;
  axis.filtered = axis.center;
  axis.low = max<int32_t>(0, axis.center - kInitialTravel);
  axis.high = min<int32_t>(kAdcMax, axis.center + kInitialTravel);
}

int16_t readAxis(Axis &axis) {
  // Average two samples and smooth the result before sizing the output.
  const int32_t first = analogRead(axis.pin);
  const int32_t sample = (first + analogRead(axis.pin)) / 2;
  axis.filtered = (axis.filtered + sample) / 2;
  axis.low = min(axis.low, axis.filtered);
  axis.high = max(axis.high, axis.filtered);
  const int32_t delta = axis.filtered - axis.center;
  const int32_t magnitude = abs(delta);
  if (magnitude <= kDeadzone) {
    return 0;
  }
  const int32_t travel = delta < 0 ? axis.center - axis.low : axis.high - axis.center;
  const int32_t scaled = (magnitude - kDeadzone) * kOutputMax / (travel - kDeadzone);
  return delta < 0 ? -scaled : scaled;
}

uint16_t readButtons(uint32_t now) {
  uint16_t mask = 0;
  for (Button &button : buttons) {
    const bool down = digitalRead(button.pin) == LOW;
    if (down != button.rawPressed) {
      button.rawPressed = down;
      button.changedAt = now;
    }
    if (now - button.changedAt >= kDebounceMs) {
      button.pressed = button.rawPressed;
    }
    if (button.pressed) {
      mask |= 1u << (button.hidUsage - 1);
    }
  }
  return mask;
}

void setup() {
  for (Button &button : buttons) {
    pinMode(button.pin, INPUT_PULLUP);
  }
  analogReadResolution(12);

  TinyUSBDevice.setProductDescriptor("Handpad 8Key L3");
  hid.setPollInterval(2);
  hid.setReportDescriptor(reportDescriptor, sizeof(reportDescriptor));
  hid.begin();
  if (TinyUSBDevice.mounted()) {
    TinyUSBDevice.detach();
    delay(15);
    TinyUSBDevice.attach();
  }

  delay(35);
  uint32_t sumX = 0;
  uint32_t sumY = 0;
  constexpr unsigned kCenterSamples = 96;
  for (unsigned i = 0; i < kCenterSamples; ++i) {
    sumX += analogRead(vrx.pin);
    sumY += analogRead(vry.pin);
    delay(2);
  }
  setCenter(vrx, sumX / kCenterSamples);
  setCenter(vry, sumY / kCenterSamples);
}

void loop() {
  const int16_t rawX = readAxis(vrx);
  const int16_t rawY = readAxis(vry);
  const int16_t x = kSwapAxes ? rawY : rawX;
  const int16_t y = kSwapAxes ? rawX : rawY;
  GamepadReport report{readButtons(millis()),
                       static_cast<int16_t>(kInvertX ? -x : x),
                       static_cast<int16_t>(kInvertY ? -y : y)};
  if (hid.ready()) {
    hid.sendReport(0, &report, sizeof(report));
  }
  delay(2);
}
