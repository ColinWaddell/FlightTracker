/**
 * Data Source page - tracking limit and weather data.
 *
 * Live provider selection and credentials moved to the Providers page
 * (provider priority lists + per-provider settings).
 */

import { defineComponent } from "./vendor.js";

export default defineComponent({
  name: "DataSourcePage",
  props: {
    store: { type: Object, required: true },
  },
  setup(props) {
    function anyFlightProviderEnabled() {
      return props.store.flightProvidersOrder.some((e) => e.enabled);
    }
    return { anyFlightProviderEnabled };
  },
  template: `
    <div>
    <h2 class="fs-4 fw-semibold mb-3"><i class="bi bi-hdd-network me-2"></i>Data Source</h2>

    <!-- ====== Flight Data ====== -->
    <div id="group-flight-data" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-airplane-engines me-2"></i>Flight Data</p>

      <div class="form-text text-muted small mb-2">
        Live flight data is fetched by your enabled
        <a href="javascript:void(0)" data-page="providers">flight providers</a> - pick and order
        them on the Providers page. FR24 is treated as an online fallback when local receivers or
        OpenSky are unavailable.
      </div>

      <hr />
      <h5>Tracking Limit</h5>
      <div>
        <label class="form-label small" for="max_flight_lookup">Flights to track</label>
        <input type="number" class="form-control form-control-sm" id="max_flight_lookup"
               name="max_flight_lookup" v-model.number="store.config.max_flight_lookup"
               min="1" max="20" style="width:6rem" />
        <div class="form-text text-warning small mt-1" v-if="anyFlightProviderEnabled()">
          <i class="bi bi-exclamation-triangle-fill me-1"></i>Flights are sorted by closest first.
          Keep this low for online providers - each flight requires a separate API call and
          higher values risk hitting rate limits.
        </div>
      </div>
    </div>

    <!-- ====== Weather Data ====== -->
    <div id="group-weather-data" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-cloud-sun me-2"></i>Weather Data</p>

      <h5>API Key</h5>
      <div class="mb-3">
        <label class="form-label small">WeatherAPI.com API Key</label>
        <input type="text" class="form-control form-control-sm"
               name="weatherapi_key" id="weatherapi_key"
               v-model="store.config.weatherapi_key"
               placeholder="Get a free key at weatherapi.com" />
        <div v-if="store.ui.weatherKeyError" class="form-text small" style="color:#dc3545">
          A WeatherAPI.com API key is required when weather is enabled.
        </div>
        <div class="form-text text-muted small">
          Weather uses your flight location coordinates.
          <a href="https://www.weatherapi.com/pricing.aspx" target="_blank">Get a free key here</a>.
        </div>
      </div>

      <hr class="my-3" />
      <h5>Refresh Interval</h5>
      <div class="mb-3">
        <label class="form-label small">Refresh interval (minutes)</label>
        <input type="number" class="form-control form-control-sm"
               name="weather_refresh_minutes" id="weather_refresh_minutes"
               v-model.number="store.config.weather_refresh_minutes"
               min="1" max="120" step="1" style="max-width:120px" />
        <div class="form-text text-muted small">How often to fetch new weather data (1-120 minutes). Lower values use more API calls.</div>
      </div>
    </div>
    </div>
  `,
});