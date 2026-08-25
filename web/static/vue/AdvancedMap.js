/**
 * Advanced location map - editable rectangle + draggable observer marker.
 *
 * Reads from / writes to the store:
 *   flight_zone_tl_y, flight_zone_tl_x, flight_zone_br_y, flight_zone_br_x,
 *   flight_observer_lat, flight_observer_lng
 */

import { defineComponent, ref, onMounted, watch, nextTick } from "./vendor.js";
import {
  createBaseMap,
  wrapLng,
  addLockControl,
  setMapInteractions,
} from "./leaflet-helpers.js";

export default defineComponent({
  name: "AdvancedMap",
  props: {
    store: { type: Object, required: true },
  },
  setup(props) {
    const mapContainer = ref(null);
    let map, rect, marker, mapLocked;

    function syncRect() {
      const bounds = rect.getBounds();
      props.store.config.flight_zone_tl_y = bounds.getNorth();
      props.store.config.flight_zone_tl_x = wrapLng(bounds.getWest());
      props.store.config.flight_zone_br_y = bounds.getSouth();
      props.store.config.flight_zone_br_x = wrapLng(bounds.getEast());
    }

    function syncMarker(lat, lng) {
      props.store.config.flight_observer_lat = lat;
      props.store.config.flight_observer_lng = lng;
    }

    function bindRectEvents(r) {
      r.on("pm:edit", syncRect);
      r.on("pm:dragend", syncRect);
      r.on("pm:resize", syncRect);
    }

    onMounted(() => {
      const cfg = props.store.config;
      const tlY = cfg.flight_zone_tl_y;
      const tlX = cfg.flight_zone_tl_x;
      const brY = cfg.flight_zone_br_y;
      const brX = cfg.flight_zone_br_x;
      const obsLat = cfg.flight_observer_lat;
      const obsLng = cfg.flight_observer_lng;

      map = createBaseMap(
        mapContainer.value,
        [obsLat, obsLng],
        10,
        { doubleClickZoom: false },
      );

      rect = L.rectangle(
        [
          [tlY, tlX],
          [brY, brX],
        ],
        { color: "#198754", weight: 2, fillOpacity: 0.1 },
      ).addTo(map);

      const obsIcon = L.divIcon({
        className: "",
        html:
          '<svg viewBox="0 0 24 24" width="28" height="28" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))"><path d="M12 0c-4.198 0-8 3.403-8 7.602 0 4.198 3.469 9.21 8 16.398 4.531-7.188 8-12.2 8-16.398 0-4.199-3.801-7.602-8-7.602zm0 11c-1.657 0-3-1.343-3-3s1.343-3 3-3 3 1.343 3 3-1.343 3-3 3z" fill="#dc3545"/></svg>',
        iconSize: [28, 28],
        iconAnchor: [14, 28],
      });
      marker = L.marker([obsLat, obsLng], {
        icon: obsIcon,
        draggable: true,
      }).addTo(map);

      map.fitBounds(rect.getBounds(), { padding: [20, 20] });

      // Enable Geoman for rectangle editing (programmatic only - no toolbar)
      map.pm.addControls({
        position: "topleft",
        drawRectangle: false,
        drawPolygon: false,
        drawCircle: false,
        drawPolyline: false,
        drawCircleMarker: false,
        drawMarker: false,
        drawText: false,
        cutPolygon: false,
        rotateMode: false,
        removalMode: false,
        editMode: false,
      });
      const pmToolbar = map.pm.getControlContainer && map.pm.getControlContainer();
      if (pmToolbar) pmToolbar.remove();

      rect.pm.enable({ snappable: false, preventIntersection: false });
      bindRectEvents(rect);

      marker.on("dragend", (e) => {
        const pos = e.target.getLatLng();
        syncMarker(pos.lat, wrapLng(pos.lng));
      });

      map.on("click", (e) => {
        if (!mapLocked) {
          const wLng = wrapLng(e.latlng.lng);
          marker.setLatLng([e.latlng.lat, wLng]);
          syncMarker(e.latlng.lat, wLng);
        }
      });

      // Double-click: set observer + centre a 10 km box
      map.on("dblclick", (e) => {
        if (mapLocked) return;
        const lat = e.latlng.lat;
        const lng = wrapLng(e.latlng.lng);
        marker.setLatLng([lat, lng]);
        syncMarker(lat, lng);
        const boxLatDeg = 10 / 111.0;
        const boxLngDeg = 10 / (111.0 * Math.cos((lat * Math.PI) / 180));
        rect.pm.disable();
        map.removeLayer(rect);
        rect = L.rectangle(
          [
            [lat + boxLatDeg, lng - boxLngDeg],
            [lat - boxLatDeg, lng + boxLngDeg],
          ],
          { color: "#198754", weight: 2, fillOpacity: 0.1 },
        ).addTo(map);
        rect.pm.enable({ snappable: false, preventIntersection: false });
        bindRectEvents(rect);
        syncRect();
        map.fitBounds(rect.getBounds(), { padding: [20, 20] });
      });

      // -- Lock state (default locked) --
      mapLocked = true;
      setMapInteractions(map, true);
      marker.dragging.disable();
      rect.pm.disable();

      addLockControl(map, (locked) => {
        mapLocked = locked;
        setMapInteractions(map, locked);
        if (locked) {
          marker.dragging.disable();
          rect.pm.disable();
        } else {
          marker.dragging.enable();
          rect.pm.enable({ snappable: false, preventIntersection: false });
        }
      }, "Toggle advanced map lock");

      // Fix tile layout after the container becomes visible.
      // The component may mount while hidden (simple mode is the default),
      // so we also watch the location mode and re-fix when it switches.
      function fixMapLayout() {
        if (mapContainer.value && mapContainer.value.offsetParent !== null) {
          map.invalidateSize();
          map.fitBounds(rect.getBounds(), { padding: [20, 20] });
        }
      }

      setTimeout(fixMapLayout, 100);

      watch(
        () => props.store.isAdvancedLocation.value,
        (isAdvanced) => {
          if (isAdvanced) nextTick(() => setTimeout(fixMapLayout, 50));
        },
      );
    });

    return { mapContainer };
  },
  template: `
    <div>
      <div ref="mapContainer" class="mb-2 advanced-map-container"></div>

      <!-- Hidden fields submitted with the form -->
      <input type="hidden" name="flight_zone_tl_y" :value="store.config.flight_zone_tl_y" />
      <input type="hidden" name="flight_zone_tl_x" :value="store.config.flight_zone_tl_x" />
      <input type="hidden" name="flight_zone_br_y" :value="store.config.flight_zone_br_y" />
      <input type="hidden" name="flight_zone_br_x" :value="store.config.flight_zone_br_x" />
      <input type="hidden" name="flight_observer_lat" :value="store.config.flight_observer_lat" />
      <input type="hidden" name="flight_observer_lng" :value="store.config.flight_observer_lng" />

      <div class="row g-2 mt-1">
        <div class="col">
          <label class="form-label small">Observer Latitude</label>
          <input type="number" step="any" class="form-control form-control-sm"
                 :value="store.config.flight_observer_lat"
                 @change="onObserverLatChange" />
        </div>
        <div class="col">
          <label class="form-label small">Observer Longitude</label>
          <input type="number" step="any" class="form-control form-control-sm"
                 :value="store.config.flight_observer_lng"
                 @change="onObserverLngChange" />
        </div>
      </div>
      <div class="form-text text-muted small mt-1">
        The search box defines the area for flight data queries. The observer marker is used for
        weather lookups, sunrise/sunset times, satellite pass prediction, and sorting flights by distance.
      </div>
    </div>
  `,
  methods: {
    onObserverLatChange(e) {
      const lat = parseFloat(e.target.value);
      if (Number.isFinite(lat)) {
        this.store.config.flight_observer_lat = lat;
      }
    },
    onObserverLngChange(e) {
      const lng = wrapLng(parseFloat(e.target.value));
      if (Number.isFinite(lng)) {
        this.store.config.flight_observer_lng = lng;
      }
    },
  },
});