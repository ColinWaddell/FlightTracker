/**
 * Data Source page - lookup priority, per-provider configuration, and
 * weather data.
 *
 * The two priority lists are reordered with up/down buttons (kept simple
 * and keyboard-accessible); the final order and enabled flags are
 * serialised into hidden <input> elements as JSON so the form submits
 * like any other page.
 *
 * The per-provider config cards are generated from the backend's field
 * descriptors (FT_PAGE_DATA.providersMeta), so adding a field to a
 * provider's ProviderConfig is all that's needed for it to appear here.
 * Sensitive fields arrive pre-masked by the backend and use mask-token
 * semantics: submitting the mask keeps the stored secret, clearing the
 * field clears the secret.
 */

import { defineComponent } from "./vendor.js";

export default defineComponent({
  name: "DataSourcePage",
  props: {
    store: { type: Object, required: true },
  },
  setup(props) {
    function move(list, index, delta) {
      const target = index + delta;
      if (target < 0 || target >= list.length) return;
      const entry = list.splice(index, 1)[0];
      list.splice(target, 0, entry);
    }

    function moveUp(list, index) {
      move(list, index, -1);
    }

    function moveDown(list, index) {
      move(list, index, 1);
    }

    function providerName(list, pid) {
      const meta = props.store.ui.providersMeta.find((p) => p.id === pid);
      return meta ? meta.name : pid;
    }

    function settingsFor(pid) {
      const providers = props.store.config.providers;
      if (!providers[pid]) providers[pid] = {};
      return providers[pid];
    }

    function providersJson(list) {
      return JSON.stringify(list.map((e) => ({ provider: e.provider, enabled: !!e.enabled })));
    }

    function anyFlightProviderEnabled() {
      return props.store.flightProvidersOrder.some((e) => e.enabled);
    }

    return {
      flightProvidersOrder: props.store.flightProvidersOrder,
      routeProvidersOrder: props.store.routeProvidersOrder,
      providersMeta: props.store.ui.providersMeta,
      moveUp,
      moveDown,
      providerName,
      settingsFor,
      providersJson,
      anyFlightProviderEnabled,
    };
  },
  template: `
    <div>
    <h2 class="fs-4 fw-semibold mb-3"><i class="bi bi-hdd-network me-2"></i>Data Source</h2>

    <!-- ====== Lookup Priority ====== -->
    <div id="group-lookup-priority" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-sort-numeric-down me-2"></i>Lookup Priority</p>

      <!-- Flight providers -->
      <h5>Aircraft monitoring <small class="text-muted ms-2">What aircraft are overhead</small></h5>
      <ul class="list-group mb-1" style="max-width:520px">
        <li v-for="(entry, index) in store.flightProvidersOrder" :key="entry.provider"
            class="list-group-item d-flex align-items-center gap-2 py-2">
          <input type="checkbox" class="form-check-input mt-0" :id="'fp-enabled-' + entry.provider"
                 v-model="entry.enabled" />
          <label class="form-check-label flex-grow-1" :for="'fp-enabled-' + entry.provider">
            {{ providerName(store.flightProvidersOrder, entry.provider) }}
          </label>
          <span v-if="!entry.enabled" class="badge text-bg-secondary">off</span>
          <button type="button" class="btn btn-sm btn-outline-secondary" :disabled="index === 0"
                  @click="moveUp(store.flightProvidersOrder, index)"
                  :aria-label="'Move ' + entry.provider + ' up'">
            <i class="bi bi-arrow-up"></i>
          </button>
          <button type="button" class="btn btn-sm btn-outline-secondary"
                  :disabled="index === store.flightProvidersOrder.length - 1"
                  @click="moveDown(store.flightProvidersOrder, index)"
                  :aria-label="'Move ' + entry.provider + ' down'">
            <i class="bi bi-arrow-down"></i>
          </button>
        </li>
      </ul>
      <input type="hidden" name="flight_providers_json"
             :value="providersJson(store.flightProvidersOrder)" />

      <!-- Route providers -->
      <h5 class="mt-3">Route and aircraft information <small class="text-muted ms-2">Details of any aircraft seen</small></h5>
      <ul class="list-group mb-2" style="max-width:520px">
        <li v-for="(entry, index) in store.routeProvidersOrder" :key="entry.provider"
            class="list-group-item d-flex align-items-center gap-2 py-2">
          <input type="checkbox" class="form-check-input mt-0" :id="'rp-enabled-' + entry.provider"
                 v-model="entry.enabled" />
          <label class="form-check-label flex-grow-1" :for="'rp-enabled-' + entry.provider">
            {{ providerName(store.routeProvidersOrder, entry.provider) }}
          </label>
          <span v-if="!entry.enabled" class="badge text-bg-secondary">off</span>
          <button type="button" class="btn btn-sm btn-outline-secondary" :disabled="index === 0"
                  @click="moveUp(store.routeProvidersOrder, index)"
                  :aria-label="'Move ' + entry.provider + ' up'">
            <i class="bi bi-arrow-up"></i>
          </button>
          <button type="button" class="btn btn-sm btn-outline-secondary"
                  :disabled="index === store.routeProvidersOrder.length - 1"
                  @click="moveDown(store.routeProvidersOrder, index)"
                  :aria-label="'Move ' + entry.provider + ' down'">
            <i class="bi bi-arrow-down"></i>
          </button>
        </li>
      </ul>
      <input type="hidden" name="route_providers_json"
             :value="providersJson(store.routeProvidersOrder)" />

      <hr class="my-3" />
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

    <!-- ====== Provider Settings (generated from descriptors) ====== -->
    <div id="group-provider-config" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-sliders me-2"></i>Provider Settings</p>

      <div v-for="meta in store.ui.providersMeta" :key="meta.id" class="mb-3 pb-3 border-bottom">
        <div class="d-flex align-items-center gap-2">
          <h5 class="mb-0">{{ meta.name }}</h5>
          <span v-if="meta.configured" class="badge text-bg-success">configured</span>
          <span v-else-if="meta.missing_required.length" class="badge text-bg-warning">
            missing {{ meta.missing_required.join(', ') }}
          </span>
          <span class="badge text-bg-light text-secondary">{{ meta.capabilities.join(' / ') }}</span>
        </div>
        <div class="form-text text-muted small" v-if="meta.description" v-html="meta.description"></div>

        <div class="row mt-2" v-if="meta.fields.length">
          <div v-for="field in meta.fields" :key="field.key" class="col-md-8 mb-2">
            <label class="form-label small mb-1" :for="'providers-' + meta.id + '-' + field.key">
              {{ field.label }}
              <span v-if="field.required" class="text-danger">*</span>
            </label>

            <input v-if="field.type === 'password'"
                   type="password" class="form-control form-control-sm"
                   :id="'providers-' + meta.id + '-' + field.key"
                   :name="'providers.' + meta.id + '.' + field.key"
                   v-model="settingsFor(meta.id)[field.key]"
                   :placeholder="field.description" autocomplete="new-password" />
            <input v-else-if="field.type === 'int'"
                   type="number" class="form-control form-control-sm"
                   :id="'providers-' + meta.id + '-' + field.key"
                   :name="'providers.' + meta.id + '.' + field.key"
                   v-model="settingsFor(meta.id)[field.key]" />
            <div v-else-if="field.type === 'bool'" class="form-check">
              <input type="checkbox" class="form-check-input"
                     :id="'providers-' + meta.id + '-' + field.key"
                     :name="'providers.' + meta.id + '.' + field.key"
                     v-model="settingsFor(meta.id)[field.key]" />
            </div>
            <input v-else
                   type="text" class="form-control form-control-sm"
                   :id="'providers-' + meta.id + '-' + field.key"
                   :name="'providers.' + meta.id + '.' + field.key"
                   v-model="settingsFor(meta.id)[field.key]"
                   :placeholder="field.description" autocomplete="off" />

            <div class="form-text text-muted small" v-if="field.description && field.type !== 'password'">
              {{ field.description }}
            </div>
          </div>
        </div>
        <div v-else class="form-text text-muted small fst-italic">
          This provider takes no configuration.
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