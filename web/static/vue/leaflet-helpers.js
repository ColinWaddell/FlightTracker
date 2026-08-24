/**
 * Shared Leaflet helpers used by both the simple and advanced map components.
 */

const WORLD_BOUNDS = L.latLngBounds([-90, -180], [90, 180]);

/** Wrap any longitude to [-180, 180) so stored values always use the primary world copy. */
export function wrapLng(lng) {
  return ((lng + 180) % 360 + 360) % 360 - 180;
}

const iconLocked =
  '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 1a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2h-1V6a5 5 0 0 0-5-5Zm-3 8V6a3 3 0 1 1 6 0v3H9Z"/></svg>';
const iconUnlocked =
  '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M17 9V7a5 5 0 0 0-9.9-1H9a3 3 0 0 1 6 0v3H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2h-1Z"/></svg>';

/**
 * Create a base Leaflet map with OSM tiles and world bounds.
 * @param {string} elementId - DOM element id for the map container
 * @param {[number, number]} center - [lat, lng]
 * @param {number} zoom
 * @param {object} [extraOpts] - extra options merged into L.map()
 * @returns {L.Map}
 */
export function createBaseMap(elementId, center, zoom, extraOpts = {}) {
  const map = L.map(elementId, {
    worldCopyJump: true,
    maxBounds: WORLD_BOUNDS,
    maxBoundsViscosity: 1.0,
    ...extraOpts,
  }).setView(center, zoom);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 18,
    noWrap: true,
  }).addTo(map);

  return map;
}

/**
 * Add a lock toggle button (top-left) that calls `onToggle` when clicked.
 * Returns nothing; the button manages its own icon state.
 *
 * @param {L.Map} map
 * @param {(locked: boolean) => void} onToggle - called with the new locked state
 * @param {string} ariaLabel
 */
export function addLockControl(map, onToggle, ariaLabel = "Toggle map lock") {
  const LockControl = L.Control.extend({
    options: { position: "topleft" },
    onAdd: function () {
      const container = L.DomUtil.create(
        "div",
        "leaflet-control leaflet-bar map-lock-control",
      );
      const button = L.DomUtil.create("button", "", container);
      button.type = "button";
      button.setAttribute("aria-label", ariaLabel);
      let locked = true;
      const render = () => {
        button.innerHTML = locked ? iconLocked : iconUnlocked;
        button.setAttribute("aria-pressed", locked ? "true" : "false");
        button.title = locked
          ? "Map locked (click to unlock)"
          : "Map unlocked (click to lock)";
      };
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      L.DomEvent.on(button, "click", (e) => {
        L.DomEvent.stop(e);
        locked = !locked;
        onToggle(locked);
        render();
      });
      render();
      return container;
    },
  });
  map.addControl(new LockControl());
}

/**
 * Add a "use my current location" button (top-left).
 * @param {L.Map} map
 * @param {() => boolean} isUnlocked - returns true if the map is currently unlocked
 * @param {(lat: number, lng: number) => void} onLocate - called with the geolocation result
 */
export function addCurrentLocationControl(map, isUnlocked, onLocate) {
  const CurrentLocationControl = L.Control.extend({
    options: { position: "topleft" },
    onAdd: function () {
      const container = L.DomUtil.create(
        "div",
        "leaflet-control leaflet-bar map-lock-control",
      );
      const button = L.DomUtil.create("button", "", container);
      button.type = "button";
      button.setAttribute("aria-label", "Use my current location");
      button.innerHTML =
        '<svg viewBox="0 0 24 24"><path d="M12 0c-4.198 0-8 3.403-8 7.602 0 4.198 3.469 9.21 8 16.398 4.531-7.188 8-12.2 8-16.398 0-4.199-3.801-7.602-8-7.602zm0 11c-1.657 0-3-1.343-3-3s1.343-3 3-3 3 1.343 3 3-1.343 3-3 3z"/></svg>';

      const updateEnabled = () => {
        const enabled = isUnlocked();
        button.disabled = !enabled;
        button.style.opacity = enabled ? "" : "0.45";
        button.title = enabled
          ? "Use my current location"
          : "Unlock the map to use current location";
      };
      updateEnabled();

      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      L.DomEvent.on(button, "click", (e) => {
        L.DomEvent.stop(e);
        if (!isUnlocked()) return;
        if (!("geolocation" in navigator)) return;
        button.disabled = true;
        button.style.opacity = "0.6";
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            const lat = pos.coords.latitude;
            const lng = pos.coords.longitude;
            if (Number.isFinite(lat) && Number.isFinite(lng)) {
              onLocate(lat, wrapLng(lng));
            }
            button.disabled = false;
            button.style.opacity = "";
          },
          () => {
            button.disabled = false;
            button.style.opacity = "";
          },
          { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
        );
      });
      return container;
    },
  });
  map.addControl(new CurrentLocationControl());
}

/**
 * Enable or disable all map interactions.
 * @param {L.Map} map
 * @param {boolean} locked
 */
export function setMapInteractions(map, locked) {
  const handlers = [
    "dragging",
    "scrollWheelZoom",
    "touchZoom",
    "doubleClickZoom",
    "boxZoom",
    "keyboard",
  ];
  for (const name of handlers) {
    const h = map[name];
    if (!h) continue;
    if (locked) h.disable();
    else h.enable();
  }
  if (map.tap) {
    if (locked) map.tap.disable();
    else map.tap.enable();
  }
}