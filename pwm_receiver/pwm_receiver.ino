// Independent, signal-only monitor for the WDR four-channel PWM bench.
// Flash this sketch to the RECEIVER board, never to the WDR bench firmware.

#include <Arduino.h>

#if CONFIG_IDF_TARGET_ESP32S3
constexpr uint8_t kPins[4] = {4, 5, 6, 7};
constexpr char kChipName[] = "ESP32-S3";
#elif CONFIG_IDF_TARGET_ESP32
// GPIO34 and 35 are input-only on the classic ESP32, which is ideal here.
constexpr uint8_t kPins[4] = {32, 33, 34, 35};
constexpr char kChipName[] = "ESP32";
#else
#error This receiver sketch supports only classic ESP32 and ESP32-S3.
#endif

struct Capture {
  volatile uint32_t rise_us = 0;
  volatile uint32_t fall_us = 0;
  volatile uint32_t width_us = 0;
  volatile uint32_t period_us = 0;
  volatile uint32_t pulses = 0;
};

Capture captures[4];
portMUX_TYPE captureMux = portMUX_INITIALIZER_UNLOCKED;

void IRAM_ATTR captureEdge(uint8_t channel) {
  const uint32_t now = micros();
  const bool high = digitalRead(kPins[channel]);
  portENTER_CRITICAL_ISR(&captureMux);
  Capture &capture = captures[channel];
  if (high) {
    if (capture.rise_us != 0) {
      const uint32_t period = now - capture.rise_us;
      if (period >= 5000 && period <= 100000) {
        capture.period_us = period;
      }
    }
    capture.rise_us = now;
  } else if (capture.rise_us != 0) {
    const uint32_t width = now - capture.rise_us;
    if (width >= 100 && width <= 5000) {
      capture.width_us = width;
      capture.fall_us = now;
      capture.pulses++;
    }
  }
  portEXIT_CRITICAL_ISR(&captureMux);
}

void IRAM_ATTR edge0() { captureEdge(0); }
void IRAM_ATTR edge1() { captureEdge(1); }
void IRAM_ATTR edge2() { captureEdge(2); }
void IRAM_ATTR edge3() { captureEdge(3); }

void setup() {
  Serial.begin(115200);
  for (uint8_t channel = 0; channel < 4; channel++) {
    pinMode(kPins[channel], INPUT);
  }
  attachInterrupt(digitalPinToInterrupt(kPins[0]), edge0, CHANGE);
  attachInterrupt(digitalPinToInterrupt(kPins[1]), edge1, CHANGE);
  attachInterrupt(digitalPinToInterrupt(kPins[2]), edge2, CHANGE);
  attachInterrupt(digitalPinToInterrupt(kPins[3]), edge3, CHANGE);
  delay(200);
  Serial.printf("WDR PWM receiver | %s | 115200 baud\n", kChipName);
  Serial.printf("Inputs: OUT0=GPIO%u OUT1=GPIO%u OUT2=GPIO%u OUT3=GPIO%u\n",
                kPins[0], kPins[1], kPins[2], kPins[3]);
  Serial.println("Expected servo PWM: approximately 20,000 us period; 500-2500 us HIGH.");
  Serial.println("NO SIGNAL means no valid pulse received in the past 100 ms.");
}

void loop() {
  static uint32_t last_report_ms = 0;
  if (millis() - last_report_ms < 250) {
    delay(5);
    return;
  }
  last_report_ms = millis();

  uint32_t width[4], period[4], last_fall[4], pulses[4];
  portENTER_CRITICAL(&captureMux);
  for (uint8_t channel = 0; channel < 4; channel++) {
    width[channel] = captures[channel].width_us;
    period[channel] = captures[channel].period_us;
    last_fall[channel] = captures[channel].fall_us;
    pulses[channel] = captures[channel].pulses;
  }
  portEXIT_CRITICAL(&captureMux);

  const uint32_t now = micros();
  Serial.printf("t=%lums", (unsigned long)millis());
  for (uint8_t channel = 0; channel < 4; channel++) {
    if (last_fall[channel] == 0 || now - last_fall[channel] > 100000) {
      Serial.printf(" | OUT%u NO SIGNAL", channel);
    } else if (period[channel] == 0) {
      Serial.printf(" | OUT%u %luus (finding period)", channel,
                    (unsigned long)width[channel]);
    } else {
      Serial.printf(" | OUT%u %luus/%luus #%lu", channel,
                    (unsigned long)width[channel], (unsigned long)period[channel],
                    (unsigned long)pulses[channel]);
    }
  }
  Serial.println();
}
