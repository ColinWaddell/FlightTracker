/**
 * Simple location map - draggable marker + search-radius circle.
 *
 * Reads from / writes to the store: flight_lat, flight_lng, flight_radius.
 * The circle is always sized in metres; the radius slider uses the
 * display unit (km or mi) via the store's computed helpers.
 */

import { defineComponent, ref, onMounted, watch, nextTick } from "./vendor.js";
import {
  createBaseMap,
  wrapLng,
  addLockControl,
  addCurrentLocationControl,
  setMapInteractions,
} from "./leaflet-helpers.js";
import { miToKm } from "./store.js";

export default defineComponent({
  name: "SimpleMap",
  props: {
    store: { type: Object, required: true },
  },
  setup(props) {
    const mapContainer = ref(null);
    let map, marker, circle, mapLocked;

    function updateLocation(lat, lng) {
      props.store.config.flight_lat = lat;
      props.store.config.flight_lng = lng;
      marker.setLatLng([lat, lng]);
      circle.setLatLng([lat, lng]);
    }

    function fitToCircle() {
      if (map && circle) {
        map.fitBounds(circle.getBounds(), { padding: [20, 20] });
      }
    }

    onMounted(() => {
      const cfg = props.store.config;
      const lat = cfg.flight_lat;
      const lng = cfg.flight_lng;
      const radiusKm = cfg.flight_radius;

      map = createBaseMap(mapContainer.value, [lat, lng], 10);
      marker = L.marker([lat, lng], { draggable: true }).addTo(map);
      circle = L.circle([lat, lng], {
        radius: radiusKm * 1000,
        color: "#0d6efd",
        fillOpacity: 0.1,
      }).addTo(map);

      map.fitBounds(circle.getBounds(), { padding: [20, 20] });

      // -- Lock state (default locked) --
      mapLocked = true;
      setMapInteractions(map, true);
      marker.dragging.disable();

      addLockControl(map, (locked) => {
        mapLocked = locked;
        setMapInteractions(map, locked);
        if (locked) marker.dragging.disable();
        else marker.dragging.enable();
      });

      addCurrentLocationControl(
        map,
        () => !mapLocked,
        (lat, lng) => {
          map.setView(L.latLng(lat, lng), map.getZoom(), { animate: true });
          updateLocation(lat, lng);
        },
      );

      // -- Marker drag --
      marker.on("dragend", (e) => {
        const pos = e.target.getLatLng();
        updateLocation(pos.lat, wrapLng(pos.lng));
      });

      // -- Click to move marker (when unlocked) --
      map.on("click", (e) => {
        if (!mapLocked) updateLocation(e.latlng.lat, wrapLng(e.latlng.lng));
      });

      // -- Radius changes -> resize circle + refit --
      watch(
        () => props.store.config.flight_radius,
        (newRadius) => {
          const km = props.store.isImperial.value
            ? miToKm(newRadius)
            : newRadius;
          circle.setRadius(km * 1000);
          fitToCircle();
        },
      );

      // Fix tile layout after the container becomes visible.
      // The component may mount while hidden (advanced mode is selected),
      // so we also watch the location mode and re-fix when it switches.
      function fixMapLayout() {
        if (mapContainer.value && mapContainer.value.offsetParent !== null) {
          map.invalidateSize();
          fitToCircle();
        }
      }

      setTimeout(fixMapLayout, 100);

      watch(
        () => props.store.isAdvancedLocation.value,
        (isAdvanced) => {
          if (!isAdvanced) nextTick(() => setTimeout(fixMapLayout, 50));
        },
      );
    });

    return { mapContainer };
  },
  template: `
    <div>
      <label class="form-label">
        <small class="text-muted">(click the unlock icon to adjust)</small>
      </label>
      <div ref="mapContainer" class="mb-2 simple-map-container"></div>

      <!-- Hidden fields submitted with the form -->
      <input type="hidden" name="flight_lat" :value="store.config.flight_lat" />
      <input type="hidden" name="flight_lng" :value="store.config.flight_lng" />

      <div class="row g-2 mt-1">
        <div class="col">
          <label class="form-label small">Latitude</label>
          <input type="number" step="any" class="form-control form-control-sm"
                 :value="store.config.flight_lat" @change="onLatChange" />
        </div>
        <div class="col">
          <label class="form-label small">Longitude</label>
          <input type="number" step="any" class="form-control form-control-sm"
                 :value="store.config.flight_lng" @change="onLngChange" />
        </div>
      </div>
    </div>
  `,
  methods: {
    onLatChange(e) {
      const lat = parseFloat(e.target.value);
      if (Number.isFinite(lat)) {
        this.store.config.flight_lat = lat;
        // The watch on flight_radius won't fire, so update marker manually
      }
    },
    onLngChange(e) {
      const lng = wrapLng(parseFloat(e.target.value));
      if (Number.isFinite(lng)) {
        this.store.config.flight_lng = lng;
      }
    },
  },
});