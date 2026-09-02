/**
 * System page - display settings, hardware, and defaults.
 */

import { defineComponent } from "./vendor.js";

export default defineComponent({
  name: "HardwarePage",
  props: {
    store: { type: Object, required: true },
  },
  computed: {
    scheduleWindowLabel() {
      const [start, end] = this.store.ui.scheduleWindow;
      if (!start || !end) return "";
      const fmt = (t) =>
        `${String(t.hour).padStart(2, "0")}:${String(t.minute).padStart(2, "0")}`;
      return `(${fmt(start)} - ${fmt(end)})`;
    },
  },
  template: `
    <div>
    <h2 class="fs-4 fw-semibold mb-3"><i class="bi bi-cpu me-2"></i>System</h2>

    <!-- ====== Display ====== -->
    <div id="group-display" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-pip me-2"></i>Display</p>

      <div class="mb-3">
        <h5>Colour Theme</h5>
        <select class="form-select form-select-sm" name="colour_theme" style="max-width:200px"
                v-model.number="store.config.colour_theme">
          <option :value="0">Default</option>
          <option :value="1">Monochrome</option>
          <option :value="2">Pastel</option>
          <option :value="3">Classic (v1)</option>
        </select>
      </div>

      <div class="mb-3">
        <h5>Animation Speed</h5>
        <select class="form-select form-select-sm" name="display_speed" style="max-width:220px"
                v-model="store.config.display_speed">
          <option value="slower">Slower</option>
          <option value="default">Default</option>
          <option value="faster">Faster</option>
        </select>
        <div class="form-text text-muted small">Adjust how quickly the display updates and animates.</div>
      </div>

      <div class="mb-3">
        <h5>Brightness</h5>
        <label class="form-label small">Level: {{ store.config.screen_brightness }}/5</label>
        <input type="range" class="form-range pt-3 px-2" name="screen_brightness" id="screen_brightness"
               min="1" max="5" step="1" v-model.number="store.config.screen_brightness"
               style="max-width:240px" />
        <div v-if="store.ui.inSchedule" class="alert alert-warning small mt-2 mb-0 py-2">
          <i class="bi bi-exclamation-triangle me-1"></i>
          The brightness schedule is currently active - changes to the default brightness
          will not take effect until the scheduled period ends
          <span v-if="store.config.screen_schedule_auto">{{ scheduleWindowLabel }}</span>.
        </div>
      </div>

      <div class="mb-2 form-check">
        <input type="checkbox" class="form-check-input" name="screen_rotate" id="screen_rotate"
               v-model="store.config.screen_rotate" />
        <label class="form-check-label" for="screen_rotate">Rotate display 180°</label>
        <div class="form-text text-muted small">Useful if you want to flip the unit and route cables from the other side.</div>
      </div>

      <hr class="my-3" />
      <h5>Brightness Schedule</h5>

      <div class="mb-2 form-check">
        <input type="checkbox" class="form-check-input" name="screen_schedule_enabled"
               id="screen_schedule_enabled" v-model="store.config.screen_schedule_enabled" />
        <label class="form-check-label" for="screen_schedule_enabled">Brightness schedule (dim at night)</label>
        <div class="form-text text-muted small">Automatically dims the screen at a set time and brightens it again in the morning.</div>
      </div>

      <div v-show="store.config.screen_schedule_enabled">
        <div class="form-check mb-2">
          <input type="checkbox" class="form-check-input" name="screen_schedule_auto" id="screen_schedule_auto"
                 v-model="store.config.screen_schedule_auto" />
          <label class="form-check-label" for="screen_schedule_auto">Automatically based on sunrise &amp; sunset</label>
          <div class="form-text text-muted small">Uses your flight location coordinates to estimate sunrise and sunset times.</div>
        </div>

        <div v-show="!store.config.screen_schedule_auto">
          <div class="row g-2 mt-1">
            <div class="col-auto">
              <label class="form-label small">Dim at</label>
              <input type="time" class="form-control form-control-sm"
                     name="screen_schedule_start" v-model="store.config.screen_schedule_start" />
            </div>
            <div class="col-auto">
              <label class="form-label small">Brighten at</label>
              <input type="time" class="form-control form-control-sm"
                     name="screen_schedule_end" v-model="store.config.screen_schedule_end" />
            </div>
          </div>
        </div>

        <div class="row g-2 mt-2">
          <div class="col-auto">
            <label class="form-label small">
              Night brightness: {{ store.config.screen_schedule_brightness }}/5 (0=off)
            </label>
            <input type="range" class="form-range pt-3 px-2" name="screen_schedule_brightness"
                   id="screen_schedule_brightness"
                   min="0" max="5" step="1" v-model.number="store.config.screen_schedule_brightness"
                   style="max-width:240px" />
            <hr />
            <div class="row">
              <div class="col-1">
                <div class="text-center" style="font-size: 2em;">💤</div>
              </div>
              <div class="col-11">
                <p>Setting a brightness of <code>0</code> in the schedule puts the device in stand-by and will
                  prevent polling of data-sources. Useful for keeping data-usage low.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ====== Hardware ====== -->
    <div id="group-hardware" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-motherboard me-2"></i>Hardware</p>

      <h5>Web Interface</h5>
      <div class="mb-2 form-check">
        <input type="checkbox" class="form-check-input" name="web_interface_enabled"
               id="web_interface_enabled" v-model="store.config.web_interface_enabled" />
        <label class="form-check-label" for="web_interface_enabled">Enable web interface on next boot</label>
        <div class="form-text text-muted small">
          If disabled, the config UI will not start and no QR code will be shown.
          Re-enable by editing <code>config.json</code> directly.
        </div>
      </div>

      <div class="mb-3">
        <label class="form-label small">Web interface port (1024-65535)</label>
        <input type="number" min="1024" max="65535" class="form-control form-control-sm"
               name="web_port" v-model.number="store.config.web_port" style="max-width:120px" />
        <div class="form-text text-muted small">TCP port for this interface. Change requires a restart.</div>
      </div>

      <hr class="my-3" />

      <div class="mb-3">
        <h5>Adafruit HAT Mode</h5>
        <div class="btn-group w-100" role="group" aria-label="Adafruit HAT mode">
          <input type="radio" class="btn-check" name="hat_pwm_enabled" id="hat_pwm_quality"
                 value="quality" autocomplete="off"
                 :checked="store.config.hat_pwm_enabled"
                 @change="store.config.hat_pwm_enabled = true" />
          <label class="btn btn-outline-primary btn-sm" for="hat_pwm_quality">Quality Mode (Adafruit PWM Enabled)</label>

          <input type="radio" class="btn-check" name="hat_pwm_enabled" id="hat_pwm_convenience"
                 value="convenience" autocomplete="off"
                 :checked="!store.config.hat_pwm_enabled"
                 @change="store.config.hat_pwm_enabled = false" />
          <label class="btn btn-outline-primary btn-sm" for="hat_pwm_convenience">Convenience Mode</label>
        </div>
        <div class="form-text text-muted small">
          If you soldered the bridge and selected Quality during setup, choose Quality Mode here to enable
          Adafruit PWM mode. Otherwise choose Convenience Mode. These options have no effect on a Pi 5; they
          only apply to older Pi models using the rgbmatrix library.
        </div>
      </div>

      <hr class="my-3" />

      <div class="mb-3">
        <h5>Display Scan Rate</h5>
        <div class="btn-group w-100" role="group" aria-label="Display Scan Rate">
          <input type="radio" class="btn-check" name="display_scan_rate" id="display_scan_rate_16"
                 value="16" autocomplete="off"
                 :checked="store.config.display_scan_rate !== 32"
                 @change="store.config.display_scan_rate = 16" />
          <label class="btn btn-outline-primary btn-sm" for="display_scan_rate_16">1:16</label>

          <input type="radio" class="btn-check" name="display_scan_rate" id="display_scan_rate_32"
                 value="32" autocomplete="off"
                 :checked="store.config.display_scan_rate === 32"
                 @change="store.config.display_scan_rate = 32" />
          <label class="btn btn-outline-primary btn-sm" for="display_scan_rate_32">1:32</label>
        </div>
        <div class="form-text text-warning small"><i class="bi bi-exclamation-triangle me-1"></i>Experimental feature.</div>
        <div class="form-text text-muted small">
          LED panels are either 1:16 or 1:32 scan rate. 64x32 panels are usually 1:16, but if you can only see
          half the image you likely have a 1:32 panel (these are normally cut-down 64x64 panels). You can sometimes
          tell from the serial number on the back of the panel &mdash; look for <code>16S</code> or <code>32S</code>.
          You will need to solder a bridge at location <code>E</code>.
          <a href="https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/matrix-setup#configure-for-64x64-matrix-3200944" target="_blank">
            There's more information here on the adafruit website.
          </a>
        </div>
      </div>

      <hr class="my-3" />

      <div class="mb-3">
        <h5>GPIO Slowdown</h5>
        <label class="form-label small">Value (1-4)</label>
        <input type="number" min="1" max="4" class="form-control form-control-sm"
               name="gpio_slowdown" v-model.number="store.config.gpio_slowdown" style="max-width:80px" />
        <div class="form-text text-muted small">Increase if you see flickering. Pi 4 usually needs 4.</div>
      </div>

      <hr class="my-3" />

      <div class="mb-3">
        <h5>Loading Indicator</h5>
        <select class="form-select form-select-sm" name="loading_indicator" id="loading_indicator"
                style="max-width:200px" v-model="store.config.loading_indicator">
          <option value="none">None</option>
          <option value="pixel">Pixel</option>
          <option value="gpio">GPIO LED</option>
        </select>
        <div class="form-text text-muted small">
          Choose how FlightTracker indicates it is searching for flights. &quot;Pixel&quot; blinks an on-screen
          pixel, &quot;GPIO LED&quot; blinks an external LED, &quot;None&quot; disables the indicator.
        </div>
      </div>

      <div v-show="store.config.loading_indicator === 'gpio'">
        <label class="form-label small mt-2">GPIO pin</label>
        <input type="number" min="1" max="40" class="form-control form-control-sm"
               name="loading_led_gpio_pin" v-model.number="store.config.loading_led_gpio_pin"
               style="max-width:80px" />
        <div class="form-text text-muted small">An external LED can be used to indicate the search for flights. Requires LED driving circuitry.</div>
      </div>

      <hr class="my-3" />

      <div class="mb-3">
        <h5>Panel Colour Order</h5>
        <select class="form-select form-select-sm" name="panel_colour_order" id="panel_colour_order"
                style="max-width:200px" v-model="store.config.panel_colour_order">
          <option value="RGB">RGB (default)</option>
          <option value="RBG">RBG</option>
          <option value="BGR">BGR</option>
          <option value="BRG">BRG</option>
          <option value="GBR">GBR</option>
          <option value="GRB">GRB</option>
        </select>
        <div class="form-text text-muted small">
          The order the red, green and blue LEDs are wired on your panel. Set this if colours appear
          swapped on the display (e.g. red shows as blue). Most panels are RGB; if yours isn't, try the
          alternative orders until the colours look right.
        </div>
      </div>
    </div>

    <!-- ====== Defaults ====== -->
    <div id="group-defaults" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-rulers me-2"></i>Defaults</p>

      <h5>Units</h5>

      <div class="mb-3">
        <label class="form-label small">Temperature</label>
        <select class="form-select form-select-sm" name="temperature_unit" style="max-width:180px"
                v-model="store.config.temperature_unit">
          <option value="c">Celsius (°C)</option>
          <option value="f">Fahrenheit (°F)</option>
          <option value="k">Kelvin (K)</option>
        </select>
        <div class="form-text text-muted small">How temperatures are shown on the display.</div>
      </div>

      <div class="mb-3">
        <label class="form-label small">Speed</label>
        <select class="form-select form-select-sm" name="speed_unit" style="max-width:180px"
                v-model="store.config.speed_unit">
          <option value="kmh">km/h</option>
          <option value="mph">mph</option>
          <option value="kts">knots</option>
        </select>
        <div class="form-text text-muted small">How aircraft and wind speeds are shown.</div>
      </div>

      <div class="mb-3">
        <label class="form-label small">Height and Distance</label>
        <select class="form-select form-select-sm" name="height_unit" style="max-width:180px"
                v-model="store.config.height_unit">
          <option value="m">Metres (m)</option>
          <option value="ft">Feet (ft)</option>
        </select>
        <div class="form-text text-muted small">How aircraft and satellite altitudes are shown.</div>
      </div>

      <div class="mb-3">
        <label class="form-label small">Number separator</label>
        <select class="form-select form-select-sm" name="number_separator" style="max-width:180px"
                v-model="store.config.number_separator">
          <option value="none">None (10000)</option>
          <option value="comma">Comma (10,000)</option>
          <option value="period">Period (10.000)</option>
        </select>
        <div class="form-text text-muted small">How large numbers are grouped in the plane details scroller.</div>
      </div>

      <hr />

      <h5>Clock and Date</h5>

      <div class="mb-2 form-check">
        <input type="checkbox" class="form-check-input" name="clock_24hr" id="clock_24hr"
               v-model="store.config.clock_24hr" />
        <label class="form-check-label" for="clock_24hr">24-hour clock</label>
      </div>

      <div class="mb-2">
        <label class="form-label small">Date format</label>
        <select class="form-select form-select-sm" name="date_format" style="max-width:200px"
                v-model.number="store.config.date_format">
          <option :value="0">YYYY-MM-DD</option>
          <option :value="1">DD-MM-YYYY</option>
          <option :value="2">MM-DD-YYYY</option>
        </select>
      </div>
    </div>
    </div>
  `,
});