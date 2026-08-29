/**
 * Data Source page - lookup priority, per-provider configuration, and
 * weather data.
 *
 * The two priority lists are reordered by dragging the grip handle on
 * each row (native HTML5 drag & drop; the handle is also a button, so
 * ArrowUp/ArrowDown reorder via keyboard).  The final order and enabled
 * flags are serialised into hidden <input> elements as JSON so the form
 * submits like any other page.
 *
 * The per-provider config cards are generated from the backend's field
 * descriptors (FT_PAGE_DATA.providersMeta), so adding a field to a
 * provider's ProviderConfig is all that's needed for it to appear here.
 * Sensitive fields arrive pre-masked by the backend and use mask-token
 * semantics: submitting the mask keeps the stored secret, clearing the
 * field clears the secret.
 */

import { defineComponent, computed, reactive, ref } from "./vendor.js";

export default defineComponent({
  name: "DataSourcePage",
  props: {
    store: { type: Object, required: true },
  },
  setup(props) {
    // --- Drag & drop reordering -------------------------------------------
    // Rows are only draggable while their grip handle is held down, so the
    // rest of the row (checkbox, label) keeps normal click/select behaviour.
    const armedKey = ref(null);
    const dragState = reactive({ listId: null, from: -1, over: -1 });

    // Provider settings cards, alphabetically by display name
    // (the backend sends them in catalogue order).
    const sortedProvidersMeta = computed(() =>
      [...props.store.ui.providersMeta].sort((a, b) =>
        a.name.localeCompare(b.name, undefined, { sensitivity: "base" })
      )
    );

    function armDrag(key) {
      armedKey.value = key;
    }

    function disarmDrag() {
      armedKey.value = null;
    }

    function listById(listId) {
      return listId === "flight"
        ? props.store.flightProvidersOrder
        : props.store.routeProvidersOrder;
    }

    function onDragStart(listId, index, event) {
      dragState.listId = listId;
      dragState.from = index;
      dragState.over = index;
      event.dataTransfer.effectAllowed = "move";
      // Required for Firefox to initiate the drag.
      event.dataTransfer.setData("text/plain", String(index));
    }

    function onDragOver(listId, index, event) {
      if (dragState.listId !== listId) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      dragState.over = index;
    }

    function onDrop(listId, index, event) {
      event.preventDefault();
      if (dragState.listId === listId && dragState.from >= 0 && dragState.from !== index) {
        const list = listById(listId);
        const entry = list.splice(dragState.from, 1)[0];
        list.splice(index, 0, entry);
      }
      onDragEnd();
    }

    function onDragEnd() {
      dragState.listId = null;
      dragState.from = -1;
      dragState.over = -1;
      disarmDrag();
    }

    function isDragging(listId, index) {
      return dragState.listId === listId && dragState.from === index;
    }

    function isDragOver(listId, index) {
      return dragState.listId === listId && dragState.over === index && dragState.from !== index;
    }

    // Keyboard fallback on the grip handle (it is a real <button>).
    function moveList(list, index, delta) {
      const target = index + delta;
      if (target < 0 || target >= list.length) return;
      const entry = list.splice(index, 1)[0];
      list.splice(target, 0, entry);
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
      sortedProvidersMeta,
      armedKey,
      armDrag,
      disarmDrag,
      onDragStart,
      onDragOver,
      onDrop,
      onDragEnd,
      isDragging,
      isDragOver,
      moveList,
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
      <p class="section-heading"><i class="bi bi-sort-numeric-down me-2"></i>Data Manager</p>

      <!-- Flight and route providers side by side (stacked on smaller screens) -->
      <div class="row g-3">
        <div class="col-12 col-lg-6">
          <h5>Aircraft monitoring<i class="bi bi-radar text-black-50 ms-2"></i></h5>
          <ul class="list-group mb-1">
            <li v-for="(entry, index) in store.flightProvidersOrder" :key="entry.provider"
                class="list-group-item d-flex align-items-center gap-2 py-2"
                :class="{ 'ft-dragging': isDragging('flight', index), 'ft-drag-over': isDragOver('flight', index) }"
                :draggable="armedKey === 'flight-' + entry.provider"
                @dragstart="onDragStart('flight', index, $event)"
                @dragover="onDragOver('flight', index, $event)"
                @drop="onDrop('flight', index, $event)"
                @dragend="onDragEnd">
              <input type="checkbox" class="form-check-input mt-0" :id="'fp-enabled-' + entry.provider"
                     v-model="entry.enabled" />
              <label class="form-check-label flex-grow-1" :for="'fp-enabled-' + entry.provider">
                {{ providerName(store.flightProvidersOrder, entry.provider) }}
              </label>
              <button type="button" class="btn btn-sm btn-outline-secondary ft-drag-handle"
                      :aria-label="'Reorder ' + entry.provider"
                      @mousedown="armDrag('flight-' + entry.provider)"
                      @keydown="armDrag('flight-' + entry.provider)"
                      @keydown.up.prevent="moveList(store.flightProvidersOrder, index, -1)"
                      @keydown.down.prevent="moveList(store.flightProvidersOrder, index, 1)"
                      @blur="disarmDrag">
                <i class="bi bi-grip-vertical"></i>
              </button>
            </li>
          </ul>
          <input type="hidden" name="flight_providers_json"
                 :value="providersJson(store.flightProvidersOrder)" />
        </div>

        <div class="col-12 col-lg-6">
          <h5>Routing and aircraft information<i class="bi bi-map text-black-50 ms-2"></i></h5>
          <ul class="list-group mb-2">
            <li v-for="(entry, index) in store.routeProvidersOrder" :key="entry.provider"
                class="list-group-item d-flex align-items-center gap-2 py-2"
                :class="{ 'ft-dragging': isDragging('route', index), 'ft-drag-over': isDragOver('route', index) }"
                :draggable="armedKey === 'route-' + entry.provider"
                @dragstart="onDragStart('route', index, $event)"
                @dragover="onDragOver('route', index, $event)"
                @drop="onDrop('route', index, $event)"
                @dragend="onDragEnd">
              <input type="checkbox" class="form-check-input mt-0" :id="'rp-enabled-' + entry.provider"
                     v-model="entry.enabled" />
              <label class="form-check-label flex-grow-1" :for="'rp-enabled-' + entry.provider">
                {{ providerName(store.routeProvidersOrder, entry.provider) }}
              </label>
              <button type="button" class="btn btn-sm btn-outline-secondary ft-drag-handle"
                      :aria-label="'Reorder ' + entry.provider"
                      @mousedown="armDrag('route-' + entry.provider)"
                      @keydown="armDrag('route-' + entry.provider)"
                      @keydown.up.prevent="moveList(store.routeProvidersOrder, index, -1)"
                      @keydown.down.prevent="moveList(store.routeProvidersOrder, index, 1)"
                      @blur="disarmDrag">
                <i class="bi bi-grip-vertical"></i>
              </button>
            </li>
          </ul>
          <input type="hidden" name="route_providers_json"
                 :value="providersJson(store.routeProvidersOrder)" />
        </div>
      </div>

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
    <div id="group-provider-config" class="mb-3">

      <h3 class="fs-4 fw-semibold my-3"><i class="bi bi-sliders me-2"></i>Provider Settings</h3>

      <div class="row g-3">
        <div v-for="meta in sortedProvidersMeta" :key="meta.id" class="col-12 col-lg-6">
          <div class="card h-100 d-flex flex-column">
            <div class="card-header">
              <h5 class="mb-0">{{ meta.name }}</h5>
            </div>
            <ul class="list-group list-group-flush">
              <li v-if="meta.description" class="list-group-item small text-muted" v-html="meta.description"></li>

              <template v-if="meta.fields.length">
                <li v-for="field in meta.fields" :key="field.key" class="list-group-item">
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
                </li>
              </template>
              <li v-else class="list-group-item small fst-italic text-muted">
                This provider takes no configuration.
              </li>
            </ul>
            <div class="card-footer mt-auto">
              <span v-if="meta.configured" class="badge text-bg-success">configured</span>
              <span v-else-if="meta.missing_required.length" class="badge text-bg-warning">
                missing {{ meta.missing_required.join(', ') }}
              </span>
              <span class="badge text-bg-light text-secondary">{{ meta.capabilities.join(' / ') }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ====== Weather Data ====== -->
    <div id="group-weather-data" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-cloud-sun me-2"></i>Weather Data</p>

      <h5>API Key</h5>
      <div class="mb-3">
        <label class="form-label small">WeatherAPI.com API Key</label>
        <input type="password" class="form-control form-control-sm"
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