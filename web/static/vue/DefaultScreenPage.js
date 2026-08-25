/**
 * Default Screen page - idle screen theme selector and per-theme settings.
 */

import { defineComponent } from "./vendor.js";

export default defineComponent({
  name: "DefaultScreenPage",
  props: {
    store: { type: Object, required: true },
  },
  computed: {
    forecastDuration: {
      get() {
        return this.store.config.theme?.forecast?.duration || "3hour";
      },
      set(val) {
        if (!this.store.config.theme) this.store.config.theme = {};
        if (!this.store.config.theme.forecast) this.store.config.theme.forecast = {};
        this.store.config.theme.forecast.duration = val;
      },
    },
    conditionsDisableScroll: {
      get() {
        return this.store.config.theme?.conditions?.disable_description_scroll || false;
      },
      set(val) {
        if (!this.store.config.theme) this.store.config.theme = {};
        if (!this.store.config.theme.conditions) this.store.config.theme.conditions = {};
        this.store.config.theme.conditions.disable_description_scroll = val;
      },
    },
  },
  template: `
    <div>
    <h2 class="fs-4 fw-semibold mb-3"><i class="bi bi-house me-2"></i>Default Screen</h2>

    <!-- ====== Theme selector ====== -->
    <div id="group-theme" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-palette me-2"></i>Theme</p>

      <div class="mb-3">
        <label class="form-label small">Idle screen theme</label>
        <select class="form-select form-select-sm" name="idle_screen_theme" id="idle_screen_theme"
                style="max-width:200px" v-model="store.config.idle_screen_theme">
          <option value="classic">Classic</option>
          <option value="conditions">Current Conditions</option>
          <option value="forecast">Forecast</option>
        </select>
        <div class="form-text text-muted small">
          Choose what to display on the idle screen when no flights or satellites are overhead.
        </div>
      </div>
    </div>

    <!-- ====== Classic theme ====== -->
    <div v-show="store.config.idle_screen_theme === 'classic'">
      <div id="group-weather" class="card mb-3 p-3">
        <p class="section-heading"><i class="bi bi-cloud-sun me-2"></i>Weather</p>

        <div class="mb-3">
          <label class="form-label small">Weather display</label>
          <div class="form-check">
            <input type="radio" class="form-check-input" name="weather_mode" id="weather_off"
                   :value="0" v-model.number="store.config.weather_mode" />
            <label class="form-check-label" for="weather_off">Off</label>
          </div>
          <div class="form-check">
            <input type="radio" class="form-check-input" name="weather_mode" id="weather_temp"
                   :value="1" v-model.number="store.config.weather_mode" />
            <label class="form-check-label" for="weather_temp">Temperature</label>
          </div>
          <div class="form-check mb-1">
            <input type="radio" class="form-check-input" name="weather_mode" id="weather_rain"
                   :value="2" v-model.number="store.config.weather_mode" />
            <label class="form-check-label" for="weather_rain">Temperature + rainfall graph</label>
          </div>
          <p class="text-muted small mb-1">
            The rainfall graph shows the forecast for the next 24 hours, hour by hour.
          </p>

          <div v-show="store.config.weather_mode === 2">
            <label class="form-label small mt-2">Rainfall sensitivity</label>
            <select class="form-select form-select-sm" name="rain_sensitivity" style="max-width:260px"
                    v-model.number="store.config.rain_sensitivity">
              <option :value="0">Not very rainy - desert / arid (1 mm)</option>
              <option :value="1">Moderately rainy - UK / Europe (3 mm)</option>
              <option :value="2">Very rainy - tropics / monsoon (9 mm)</option>
            </select>
            <div class="form-text text-muted small">
              Sets the full-scale value of the graph. Increase if your bars are always full; decrease if they're always empty.
            </div>
          </div>
        </div>

        <div class="card bg-light p-3 mb-3">
          <h5 class="pb-3">How the rainfall graph works</h5>
          <div class="row g-3 align-items-center pb-3">
            <div class="col-12 col-sm-5 text-center">
              <img :src="store.ui.staticUrls.weatherExplained" class="img-fluid mx-auto d-block"
                   style="max-height:150px;" alt="Weather graph example" />
            </div>
            <div class="col-12 col-sm-7">
              <p class="small mb-1">Each column is one hour, the leftmost is <strong>now</strong>.</p>
              <p class="small mb-0">The height of the column shows how much rain is expected that hour.</p>
            </div>
          </div>
          <hr class="pb-3">
          <div class="row g-3 align-items-center">
            <div class="col-12 col-sm-5 text-center">
              <img :src="store.ui.staticUrls.scaleExplained" class="img-fluid mx-auto d-block"
                   style="max-height:75px" alt="Temperature colour scale" />
            </div>
            <div class="col-12 col-sm-7">
              <p class="small mb-0">The colour of each column shows the temperature at that hour.</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ====== Forecast theme ====== -->
    <div v-show="store.config.idle_screen_theme === 'forecast'">
      <div class="card mb-3 p-3">
        <p class="section-heading"><i class="bi bi-cloud-sun-fill me-2"></i>Forecast</p>
        <p class="text-muted small mb-0">Display upcoming weather forecasts as icons on the idle screen.</p>
      </div>
      <div class="card mb-3 p-3">
        <p class="section-heading"><i class="bi bi-clock-history me-2"></i>Forecast Duration</p>
        <div class="mb-3">
          <label class="form-label small">Forecast type</label>
          <div class="form-check">
            <input type="radio" class="form-check-input" name="theme_forecast_duration"
                   id="forecast_duration_3hour" value="3hour" v-model="forecastDuration" />
            <label class="form-check-label" for="forecast_duration_3hour">3 hour (now + next 2 hours)</label>
          </div>
          <div class="form-check">
            <input type="radio" class="form-check-input" name="theme_forecast_duration"
                   id="forecast_duration_12hour" value="12hour" v-model="forecastDuration" />
            <label class="form-check-label" for="forecast_duration_12hour">12 hour (now + 4h + 8h)</label>
          </div>
          <div class="form-check">
            <input type="radio" class="form-check-input" name="theme_forecast_duration"
                   id="forecast_duration_3day" value="3day" v-model="forecastDuration" />
            <label class="form-check-label" for="forecast_duration_3day">3 day (today + next 2 days)</label>
          </div>
          <div class="form-text text-muted small">Choose how far ahead the forecast display looks.</div>
        </div>
      </div>
    </div>

    <!-- ====== Current Conditions theme ====== -->
    <div v-show="store.config.idle_screen_theme === 'conditions'">
      <div class="card mb-3 p-3">
        <p class="section-heading"><i class="bi bi-thermometer-half me-2"></i>Current Conditions</p>
        <p class="text-muted small mb-0">
          Display the current weather at a glance: a weather sprite, temperature, humidity, wind, UV index,
          moon-phase and sunrise/sunset.
        </p>
      </div>
      <div class="card mb-3 p-3">
        <p class="section-heading"><i class="bi bi-card-text me-2"></i>Description</p>
        <div class="mb-2 form-check">
          <input type="checkbox" class="form-check-input" name="theme_conditions_disable_scroll"
                 id="theme_conditions_disable_scroll" v-model="conditionsDisableScroll" />
          <label class="form-check-label" for="theme_conditions_disable_scroll">Disable scrolling weather description</label>
        </div>
      </div>
    </div>
    </div>
  `,
});