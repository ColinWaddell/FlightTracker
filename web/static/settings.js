/* ===== FlightTracker settings page logic ===== */
/* Expects: window.FT_AIRPORTS (JSON object of airport codes -> names) */
/* Expects: Leaflet (L), Geoman, Vue, VueRouter to be loaded already   */

(function () {
  "use strict";

  const AIRPORTS = window.FT_AIRPORTS || {};

  // ===========================================================================
  // Vue Router setup (hash mode)
  // ===========================================================================
  const { createApp } = Vue;
  const { createRouter, createWebHashHistory } = VueRouter;

  const routes = [
    { path: "/", redirect: "/sky-monitoring" },
    { path: "/sky-monitoring", component: { template: "<div/>" } },
    { path: "/data-source",        component: { template: "<div/>" } },
    { path: "/default-screen",     component: { template: "<div/>" } },
    { path: "/hardware",           component: { template: "<div/>" } },
    { path: "/admin",              component: { template: "<div/>" } },
  ];

  const router = createRouter({
    history: createWebHashHistory(),
    routes,
    linkActiveClass: "",
    linkExactActiveClass: "",
  });

  // -- Page visibility + scroll-to-section on navigation --
  const PAGES = ["sky-monitoring", "data-source", "default-screen", "hardware", "admin"];
  let pendingSection = null;

  function showPage(pageName) {
    PAGES.forEach(p => {
      const el = document.getElementById("page-" + p);
      if (el) el.classList.toggle("active", p === pageName);
    });
  }

  function highlightSidebarItem(section) {
    document.querySelectorAll("#settings-sidebar .nav-link").forEach(l => l.classList.remove("nav-link-selected"));
    if (section) {
      const link = document.querySelector('#settings-sidebar .nav-link[data-section="' + section + '"]');
      if (link) link.classList.add("nav-link-selected");
    }
  }

  router.afterEach((to) => {
    const pageName = to.path.replace(/^\//, "");
    showPage(pageName);

    const section = pendingSection;
    pendingSection = null;

    highlightSidebarItem(section);

    if (section) {
      setTimeout(() => {
        const target = document.getElementById(section);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 80);
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    // Fix Leaflet tile layout when the Sky Monitoring page becomes visible
    if (pageName === "sky-monitoring") {
      setTimeout(() => {
        if (typeof map !== "undefined" && document.getElementById("simple_tracking").style.display !== "none") {
          map.invalidateSize();
          map.fitBounds(circle.getBounds(), { padding: [20, 20] });
        }
        if (typeof advMap !== "undefined" && document.getElementById("advanced_tracking").style.display !== "none") {
          advMap.invalidateSize();
          advMap.fitBounds(advRect.getBounds(), { padding: [20, 20] });
        }
      }, 100);
    }
  });

  // Intercept sidebar link clicks that carry a data-section attribute so we
  // can scroll to the sub-section even when already on that page.
  document.addEventListener("click", (e) => {
    const link = e.target.closest("a[data-section]");
    if (!link) return;
    const section = link.getAttribute("data-section");
    const href = link.getAttribute("href") || "";
    const targetPage = href.replace(/^#\/?/, "");
    const currentPath = router.currentRoute.value.path.replace(/^\//, "");
    pendingSection = section;
    if (currentPath === targetPage) {
      e.preventDefault();
      highlightSidebarItem(section);
      const target = document.getElementById(section);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      pendingSection = null;
    }
  });

  createApp({}).use(router).mount("#settings-sidebar");

  // ===========================================================================
  // Data source radio toggle
  // ===========================================================================
  (function () {
    const fr24Radio      = document.getElementById("data_source_fr24");
    const tar1090Radio   = document.getElementById("data_source_tar1090");
    const osnRadio       = document.getElementById("data_source_osn");
    const tar1090Fields  = document.getElementById("tar1090_fields");
    const osnFields      = document.getElementById("osn_fields");
    const fr24Warning    = document.getElementById("fr24_lookup_warning");
    const callsignFields = document.getElementById("callsign_format_fields");

    function updateDataSourceUI() {
      const isFr24    = fr24Radio.checked;
      const isTar1090 = tar1090Radio.checked;
      const isOsn     = osnRadio.checked;
      tar1090Fields.style.display  = isTar1090 ? "block" : "none";
      osnFields.style.display      = isOsn     ? "block" : "none";
      fr24Warning.style.display    = isFr24    ? "block" : "none";
    }

    fr24Radio.addEventListener("change", updateDataSourceUI);
    tar1090Radio.addEventListener("change", updateDataSourceUI);
    osnRadio.addEventListener("change", updateDataSourceUI);
  })();

  // ===========================================================================
  // Satellite tracking toggle
  // ===========================================================================
  (function () {
    const satEnabled = document.getElementById("satellite_tracking_enabled");
    const satFields  = document.getElementById("satellite_fields");
    satEnabled.addEventListener("change", function () {
      satFields.style.display = satEnabled.checked ? "block" : "none";
    });
  })();

  // ===========================================================================
  // Leaflet maps
  // ===========================================================================

  // -- World bounds: prevent panning/zooming beyond a single Earth copy --
  const WORLD_BOUNDS = L.latLngBounds([-90, -180], [90, 180]);

  // -- Normalise any longitude to [-180, 180) so markers and stored values --
  // -- always use the primary world copy, even if the user clicked on a  --
  // -- repeated tile copy at lng > 180 or lng < -180.                     --
  function wrapLng(lng) {
    return ((lng + 180) % 360 + 360) % 360 - 180;
  }

  // -- Simple map --
  const initLat = parseFloat(document.getElementById("flight_lat").value) || 55.87;
  const initLng = parseFloat(document.getElementById("flight_lng").value) || -4.25;
  const initRadius = parseFloat(document.getElementById("flight_radius").value) || 20;

  // ===========================================================================
  // Height / distance unit helpers (metric ↔ imperial)
  // ===========================================================================
  // The backend always stores flight_radius in km and altitudes in metres.
  // When height_unit is "ft" we display radius in miles and altitudes in feet,
  // converting back to the stored units just before the form is submitted.
  const FT_PER_M = 3.28084;
  const MI_PER_KM = 0.621371;
  const mToFt = (m) => m * FT_PER_M;
  const ftToM = (ft) => ft / FT_PER_M;
  const kmToMi = (km) => km * MI_PER_KM;
  const miToKm = (mi) => mi / MI_PER_KM;

  // Slider / input bounds expressed in the *stored* (metric) unit.
  const RADIUS_BOUNDS = { min: 1, max: 100, step: 0.5 };          // km
  const MIN_ALT_BOUNDS = { min: 10, max: 20000, step: 10 };       // metres
  const MAX_ALT_BOUNDS = { min: 100, max: 40000, step: 100 };     // metres

  function isImperial() {
    const sel = document.querySelector('select[name="height_unit"]');
    return sel ? sel.value === "ft" : false;
  }

  // Track which unit the fields are *currently displayed in* so we know how
  // to interpret the existing input values when toggling.  Jinja renders the
  // raw stored values (metric) on page load, so we start as metric.
  let fieldsAreImperial = false;

  // Convert the radius / altitude fields between metric and imperial for
  // display.  The Leaflet circle is always sized in metres so the map stays
  // physically correct regardless of the chosen unit.
  function applyUnitToFields() {
    const imperial = isImperial();
    const radiusInput = document.getElementById("flight_radius");
    const radiusDisplay = document.getElementById("radius_display");
    const radiusUnitLabel = document.getElementById("radius_unit_label");
    const minAltInput = document.getElementById("flight_min_altitude");
    const maxAltInput = document.getElementById("flight_max_altitude");
    const minAltLabel = document.getElementById("min_alt_unit_label");
    const maxAltLabel = document.getElementById("max_alt_unit_label");
    const helpText = document.getElementById("altitude_help_text");

    // No-op if the display unit hasn't changed (e.g. re-called on load after
    // already being in the right unit).
    if (imperial === fieldsAreImperial) {
      // Still update labels + circle in case this is the first call.
      radiusUnitLabel.textContent = imperial ? "mi" : "km";
      minAltLabel.textContent = imperial ? "ft" : "m";
      maxAltLabel.textContent = imperial ? "ft" : "m";
    } else {
      // -- Convert existing values from the current display unit to the new one --
      // Radius: km ↔ miles
      const curRadius = parseFloat(radiusInput.value) || RADIUS_BOUNDS.min;
      const newRadius = imperial ? kmToMi(curRadius) : miToKm(curRadius);
      radiusInput.min = imperial
        ? (RADIUS_BOUNDS.min * MI_PER_KM).toFixed(3)
        : RADIUS_BOUNDS.min;
      radiusInput.max = imperial
        ? (RADIUS_BOUNDS.max * MI_PER_KM).toFixed(3)
        : RADIUS_BOUNDS.max;
      radiusInput.step = imperial
        ? (RADIUS_BOUNDS.step * MI_PER_KM).toFixed(3)
        : RADIUS_BOUNDS.step;
      radiusInput.value = imperial ? newRadius.toFixed(3) : newRadius;
      radiusUnitLabel.textContent = imperial ? "mi" : "km";

      // Min altitude: metres ↔ feet
      const curMinAlt = parseFloat(minAltInput.value) || MIN_ALT_BOUNDS.min;
      const newMinAlt = imperial ? mToFt(curMinAlt) : ftToM(curMinAlt);
      minAltInput.min = imperial
        ? (MIN_ALT_BOUNDS.min * FT_PER_M).toFixed(0)
        : MIN_ALT_BOUNDS.min;
      minAltInput.max = imperial
        ? (MIN_ALT_BOUNDS.max * FT_PER_M).toFixed(0)
        : MIN_ALT_BOUNDS.max;
      minAltInput.step = imperial
        ? (MIN_ALT_BOUNDS.step * FT_PER_M).toFixed(0)
        : MIN_ALT_BOUNDS.step;
      minAltInput.value = Math.round(newMinAlt);
      minAltLabel.textContent = imperial ? "ft" : "m";

      // Max altitude: metres ↔ feet
      const curMaxAlt = parseFloat(maxAltInput.value) || MAX_ALT_BOUNDS.min;
      const newMaxAlt = imperial ? mToFt(curMaxAlt) : ftToM(curMaxAlt);
      maxAltInput.min = imperial
        ? (MAX_ALT_BOUNDS.min * FT_PER_M).toFixed(0)
        : MAX_ALT_BOUNDS.min;
      maxAltInput.max = imperial
        ? (MAX_ALT_BOUNDS.max * FT_PER_M).toFixed(0)
        : MAX_ALT_BOUNDS.max;
      maxAltInput.step = imperial
        ? (MAX_ALT_BOUNDS.step * FT_PER_M).toFixed(0)
        : MAX_ALT_BOUNDS.step;
      maxAltInput.value = Math.round(newMaxAlt);
      maxAltLabel.textContent = imperial ? "ft" : "m";

      fieldsAreImperial = imperial;
    }

    radiusDisplay.textContent = radiusInput.value;

    // -- Help text example value --
    if (helpText) {
      const exampleVal = imperial ? "30ft" : "10m";
      helpText.innerHTML =
        '<i class="bi bi-info-circle me-1"></i>Setting a non-zero minimum altitude (say, <code>'
        + exampleVal + '</code>) prevents the device always listing aircraft on the tarmac.';
    }

    // -- Keep the Leaflet circle in sync (always metres) --
    if (typeof circle !== "undefined") {
      const displayRadius = parseFloat(radiusInput.value) || RADIUS_BOUNDS.min;
      const radiusKm = imperial ? miToKm(displayRadius) : displayRadius;
      circle.setRadius(radiusKm * 1000);
      if (typeof map !== "undefined") {
        map.fitBounds(circle.getBounds(), { padding: [20, 20] });
      }
    }
  }

  const map = L.map("map", {
    worldCopyJump: true,
    maxBounds: WORLD_BOUNDS,
    maxBoundsViscosity: 1.0,
  }).setView([initLat, initLng], 10);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors", maxZoom: 18, noWrap: true,
  }).addTo(map);

  let marker = L.marker([initLat, initLng], { draggable: true }).addTo(map);
  let circle = L.circle([initLat, initLng], { radius: initRadius * 1000, color: "#0d6efd", fillOpacity: 0.1 }).addTo(map);

  // Expose map objects for inline onchange handlers
  window.map = map;
  window.circle = circle;

  map.fitBounds(circle.getBounds(), { padding: [20, 20] });

  // -- Map lock state (default locked) --
  let mapLocked = true;
  let currentLocationButton = null;

  function setCurrentLocationEnabled(enabled) {
    if (!currentLocationButton) return;
    currentLocationButton.disabled = !enabled;
    currentLocationButton.style.opacity = enabled ? "" : "0.45";
    currentLocationButton.title = enabled ? "Use my current location" : "Unlock the map to use current location";
  }

  function setMapLocked(locked) {
    const enable = (h) => h && h.enable && h.enable();
    const disable = (h) => h && h.disable && h.disable();
    mapLocked = locked;
    setCurrentLocationEnabled(!locked);
    document.getElementById("lat_display").disabled = locked;
    document.getElementById("lng_display").disabled = locked;
    if (locked) {
      disable(map.dragging);
      disable(map.scrollWheelZoom);
      disable(map.touchZoom);
      disable(map.doubleClickZoom);
      disable(map.boxZoom);
      disable(map.keyboard);
      if (map.tap) disable(map.tap);
      marker.dragging.disable();
    } else {
      enable(map.dragging);
      enable(map.scrollWheelZoom);
      enable(map.touchZoom);
      enable(map.doubleClickZoom);
      enable(map.boxZoom);
      enable(map.keyboard);
      if (map.tap) enable(map.tap);
      marker.dragging.enable();
    }
  }

  const iconLocked = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 1a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2h-1V6a5 5 0 0 0-5-5Zm-3 8V6a3 3 0 1 1 6 0v3H9Z"/></svg>';
  const iconUnlocked = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M17 9V7a5 5 0 0 0-9.9-1H9a3 3 0 0 1 6 0v3H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2h-1Z"/></svg>';

  const LockControl = L.Control.extend({
    options: { position: "topleft" },
    onAdd: function () {
      const container = L.DomUtil.create("div", "leaflet-control leaflet-bar map-lock-control");
      const button = L.DomUtil.create("button", "", container);
      button.type = "button";
      button.setAttribute("aria-label", "Toggle map lock");
      let locked = true;
      const render = () => {
        button.innerHTML = locked ? iconLocked : iconUnlocked;
        button.setAttribute("aria-pressed", locked ? "true" : "false");
        button.title = locked ? "Map locked (click to unlock)" : "Map unlocked (click to lock)";
      };
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      L.DomEvent.on(button, "click", (e) => {
        L.DomEvent.stop(e);
        locked = !locked;
        setMapLocked(locked);
        render();
      });
      render();
      return container;
    }
  });

  const CurrentLocationControl = L.Control.extend({
    options: { position: "topleft" },
    onAdd: function () {
      const container = L.DomUtil.create("div", "leaflet-control leaflet-bar map-lock-control");
      const button = L.DomUtil.create("button", "", container);
      button.type = "button";
      button.setAttribute("aria-label", "Use my current location");
      button.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 0c-4.198 0-8 3.403-8 7.602 0 4.198 3.469 9.21 8 16.398 4.531-7.188 8-12.2 8-16.398 0-4.199-3.801-7.602-8-7.602zm0 11c-1.657 0-3-1.343-3-3s1.343-3 3-3 3 1.343 3 3-1.343 3-3 3z"/></svg>';
      currentLocationButton = button;
      setCurrentLocationEnabled(!mapLocked);
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      L.DomEvent.on(button, "click", (e) => {
        L.DomEvent.stop(e);
        if (mapLocked) return;
        if (!("geolocation" in navigator)) return;
        button.disabled = true;
        button.style.opacity = "0.6";
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            const lat = pos.coords.latitude;
            const lng = pos.coords.longitude;
            if (Number.isFinite(lat) && Number.isFinite(lng)) {
              const wLng = wrapLng(lng);
              map.setView(L.latLng(lat, wLng), map.getZoom(), { animate: true });
              marker.setLatLng([lat, wLng]);
              circle.setLatLng([lat, wLng]);
              updateLocation(lat, wLng);
            }
            button.disabled = false;
            button.style.opacity = "";
          },
          () => {
            button.disabled = false;
            button.style.opacity = "";
          },
          { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
      });
      return container;
    }
  });

  map.addControl(new LockControl());
  map.addControl(new CurrentLocationControl());
  setMapLocked(true);

  function updateLocation(lat, lng) {
    document.getElementById("flight_lat").value = lat.toFixed(6);
    document.getElementById("flight_lng").value = lng.toFixed(6);
    document.getElementById("lat_display").value = lat.toFixed(6);
    document.getElementById("lng_display").value = lng.toFixed(6);
    marker.setLatLng([lat, lng]);
    circle.setLatLng([lat, lng]);
  }

  marker.on("dragend", e => {
    const pos = e.target.getLatLng();
    updateLocation(pos.lat, wrapLng(pos.lng));
  });

  map.on("click", e => { if (!mapLocked) updateLocation(e.latlng.lat, wrapLng(e.latlng.lng)); });

  document.getElementById("lat_display").addEventListener("change", () => {
    updateLocation(parseFloat(document.getElementById("lat_display").value), wrapLng(parseFloat(document.getElementById("lng_display").value)));
  });
  document.getElementById("lng_display").addEventListener("change", () => {
    updateLocation(parseFloat(document.getElementById("lat_display").value), wrapLng(parseFloat(document.getElementById("lng_display").value)));
  });

  // -- Radius slider --
  document.getElementById("flight_radius").addEventListener("input", e => {
    const r = parseFloat(e.target.value);
    document.getElementById("radius_display").textContent = r;
    const radiusKm = isImperial() ? miToKm(r) : r;
    circle.setRadius(radiusKm * 1000);
    map.fitBounds(circle.getBounds(), { padding: [20, 20] });
  });

  // -- Height / distance unit toggle --
  // Re-render the radius + altitude fields in the newly selected unit.
  const heightUnitSelect = document.querySelector('select[name="height_unit"]');
  if (heightUnitSelect) {
    heightUnitSelect.addEventListener("change", applyUnitToFields);
  }

  // Apply the stored unit preference to the fields on first load (after the
  // map + circle are ready).
  applyUnitToFields();

  // ===========================================================================
  // Advanced map - editable rectangle + draggable observer marker
  // ===========================================================================
  const advTlY = parseFloat(document.getElementById("flight_zone_tl_y").value);
  const advTlX = parseFloat(document.getElementById("flight_zone_tl_x").value);
  const advBrY = parseFloat(document.getElementById("flight_zone_br_y").value);
  const advBrX = parseFloat(document.getElementById("flight_zone_br_x").value);
  const advObsLat = parseFloat(document.getElementById("flight_observer_lat").value);
  const advObsLng = parseFloat(document.getElementById("flight_observer_lng").value);

  const advMap = L.map("map_advanced", {
    doubleClickZoom: false,
    worldCopyJump: true,
    maxBounds: WORLD_BOUNDS,
    maxBoundsViscosity: 1.0,
  }).setView([advObsLat, advObsLng], 10);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors", maxZoom: 18, noWrap: true,
  }).addTo(advMap);

  // Editable rectangle for the search box
  let advRect = L.rectangle(
    [[advTlY, advTlX], [advBrY, advBrX]],
    { color: "#198754", weight: 2, fillOpacity: 0.1 }
  ).addTo(advMap);

  // Draggable observer marker (different colour via icon)
  const obsIcon = L.divIcon({
    className: "",
    html: '<svg viewBox="0 0 24 24" width="28" height="28" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))"><path d="M12 0c-4.198 0-8 3.403-8 7.602 0 4.198 3.469 9.21 8 16.398 4.531-7.188 8-12.2 8-16.398 0-4.199-3.801-7.602-8-7.602zm0 11c-1.657 0-3-1.343-3-3s1.343-3 3-3 3 1.343 3 3-1.343 3-3 3z" fill="#dc3545"/></svg>',
    iconSize: [28, 28],
    iconAnchor: [14, 28],
  });
  let advMarker = L.marker([advObsLat, advObsLng], {
    icon: obsIcon,
    draggable: true,
  }).addTo(advMap);

  // Expose advanced map objects for inline onchange handlers
  window.advMap = advMap;
  window.advRect = advRect;

  advMap.fitBounds(advRect.getBounds(), { padding: [20, 20] });

  // Enable Geoman for rectangle editing (programmatic only - no toolbar)
  advMap.pm.addControls({
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
  // Remove the Geoman toolbar from the DOM - we only need the programmatic API
  const pmToolbar = advMap.pm.getControlContainer && advMap.pm.getControlContainer();
  if (pmToolbar) pmToolbar.remove();

  // Allow the rectangle to be edited (drag corners / edges)
  advRect.pm.enable({
    snappable: false,
    preventIntersection: false,
  });

  // Sync rectangle corners to hidden inputs on edit
  advRect.on("pm:edit", () => syncAdvRect());
  advRect.on("pm:dragend", () => syncAdvRect());
  advRect.on("pm:resize", () => syncAdvRect());

  function syncAdvRect() {
    const bounds = advRect.getBounds();
    document.getElementById("flight_zone_tl_y").value = bounds.getNorth().toFixed(6);
    document.getElementById("flight_zone_tl_x").value = wrapLng(bounds.getWest()).toFixed(6);
    document.getElementById("flight_zone_br_y").value = bounds.getSouth().toFixed(6);
    document.getElementById("flight_zone_br_x").value = wrapLng(bounds.getEast()).toFixed(6);
  }

  // Sync observer marker to hidden inputs + display fields
  function syncAdvMarker(lat, lng) {
    document.getElementById("flight_observer_lat").value = lat.toFixed(6);
    document.getElementById("flight_observer_lng").value = lng.toFixed(6);
    document.getElementById("observer_lat_display").value = lat.toFixed(6);
    document.getElementById("observer_lng_display").value = lng.toFixed(6);
  }

  advMarker.on("dragend", e => {
    const pos = e.target.getLatLng();
    syncAdvMarker(pos.lat, wrapLng(pos.lng));
  });

  advMap.on("click", e => {
    if (!advMapLocked) {
      const wLng = wrapLng(e.latlng.lng);
      advMarker.setLatLng([e.latlng.lat, wLng]);
      syncAdvMarker(e.latlng.lat, wLng);
    }
  });

  // Double-click: set observer + centre a 10 km box around the location
  advMap.on("dblclick", e => {
    if (advMapLocked) return;
    const lat = e.latlng.lat;
    const lng = wrapLng(e.latlng.lng);
    advMarker.setLatLng([lat, lng]);
    syncAdvMarker(lat, lng);
    const boxLatDeg = 10 / 111.0;
    const boxLngDeg = 10 / (111.0 * Math.cos(lat * Math.PI / 180));
    // Disable Geoman editing, remove old rect, create a fresh one
    advRect.pm.disable();
    advMap.removeLayer(advRect);
    advRect = L.rectangle(
      [[lat + boxLatDeg, lng - boxLngDeg], [lat - boxLatDeg, lng + boxLngDeg]],
      { color: "#198754", weight: 2, fillOpacity: 0.1 }
    ).addTo(advMap);
    advRect.pm.enable({ snappable: false, preventIntersection: false });
    advRect.on("pm:edit", () => syncAdvRect());
    advRect.on("pm:dragend", () => syncAdvRect());
    advRect.on("pm:resize", () => syncAdvRect());
    syncAdvRect();
    advMap.fitBounds(advRect.getBounds(), { padding: [20, 20] });
  });

  document.getElementById("observer_lat_display").addEventListener("change", () => {
    const lat = parseFloat(document.getElementById("observer_lat_display").value);
    const lng = wrapLng(parseFloat(document.getElementById("observer_lng_display").value));
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      advMarker.setLatLng([lat, lng]);
      syncAdvMarker(lat, lng);
    }
  });
  document.getElementById("observer_lng_display").addEventListener("change", () => {
    const lat = parseFloat(document.getElementById("observer_lat_display").value);
    const lng = wrapLng(parseFloat(document.getElementById("observer_lng_display").value));
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      advMarker.setLatLng([lat, lng]);
      syncAdvMarker(lat, lng);
    }
  });

  // -- Advanced map lock state (default locked) --
  let advMapLocked = true;

  function setAdvMapLocked(locked) {
    advMapLocked = locked;
    document.getElementById("observer_lat_display").disabled = locked;
    document.getElementById("observer_lng_display").disabled = locked;
    if (locked) {
      advMap.dragging.disable();
      advMap.scrollWheelZoom.disable();
      advMap.touchZoom.disable();
      advMap.doubleClickZoom.disable();
      advMap.boxZoom.disable();
      advMap.keyboard.disable();
      if (advMap.tap) advMap.tap.disable();
      advMarker.dragging.disable();
      advRect.pm.disable();
    } else {
      advMap.dragging.enable();
      advMap.scrollWheelZoom.enable();
      advMap.touchZoom.enable();
      advMap.doubleClickZoom.enable();
      advMap.boxZoom.enable();
      advMap.keyboard.enable();
      if (advMap.tap) advMap.tap.enable();
      advMarker.dragging.enable();
      advRect.pm.enable({ snappable: false, preventIntersection: false });
    }
  }

  const AdvLockControl = L.Control.extend({
    options: { position: "topleft" },
    onAdd: function () {
      const container = L.DomUtil.create("div", "leaflet-control leaflet-bar map-lock-control");
      const button = L.DomUtil.create("button", "", container);
      button.type = "button";
      button.setAttribute("aria-label", "Toggle advanced map lock");
      let locked = true;
      const render = () => {
        button.innerHTML = locked ? iconLocked : iconUnlocked;
        button.setAttribute("aria-pressed", locked ? "true" : "false");
        button.title = locked ? "Map locked (click to unlock)" : "Map unlocked (click to lock)";
      };
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      L.DomEvent.on(button, "click", (e) => {
        L.DomEvent.stop(e);
        locked = !locked;
        setAdvMapLocked(locked);
        render();
      });
      render();
      return container;
    }
  });

  advMap.addControl(new AdvLockControl());
  setAdvMapLocked(true);

  // If the page loads in advanced mode, the simple map was initialised while hidden.
  // Fix the tile layout and zoom to fit the circle once the browser has laid out the container.
  setTimeout(function () {
    if (document.getElementById("simple_tracking").style.display !== "none") {
      map.invalidateSize();
      map.fitBounds(circle.getBounds(), { padding: [20, 20] });
    }
  }, 100);

  // If the page loads in advanced mode, the advanced map was initialised while hidden.
  // Fix the tile layout and zoom to fit the rectangle once the browser has laid out the container.
  setTimeout(function () {
    if (document.getElementById("advanced_tracking").style.display !== "none") {
      advMap.invalidateSize();
      advMap.fitBounds(advRect.getBounds(), { padding: [20, 20] });
    }
  }, 100);

  // ===========================================================================
  // Brightness sliders
  // ===========================================================================
  document.getElementById("screen_brightness").addEventListener("input", e => {
    document.getElementById("brightness_display").textContent = e.target.value;
  });
  document.getElementById("screen_schedule_brightness").addEventListener("input", e => {
    document.getElementById("night_brightness_display").textContent = e.target.value;
  });

  // ===========================================================================
  // Airport name hint
  // ===========================================================================
  document.getElementById("home_airport_code").addEventListener("input", e => {
    const code = e.target.value.toUpperCase();
    e.target.value = code;
    const hint = document.getElementById("airport_name_hint");
    hint.textContent = AIRPORTS[code]?.name ?? (code.length >= 3 ? "Unknown airport" : "");
  });

  // Trigger on load
  (function () {
    const code = document.getElementById("home_airport_code").value.toUpperCase();
    const hint = document.getElementById("airport_name_hint");
    hint.textContent = AIRPORTS[code]?.name ?? "";
  })();

  // ===========================================================================
  // Idle screen theme selector
  // ===========================================================================
  window.updateIdleThemeSections = function updateIdleThemeSections() {
    const sel = document.getElementById("idle_screen_theme");
    if (!sel) return;
    const theme = sel.value;
    const classic = document.getElementById("idle-theme-classic");
    const forecast = document.getElementById("idle-theme-forecast");
    const conditions = document.getElementById("idle-theme-conditions");
    if (classic) classic.style.display = theme === "classic" ? "block" : "none";
    if (forecast) forecast.style.display = theme === "forecast" ? "block" : "none";
    if (conditions) conditions.style.display = theme === "conditions" ? "block" : "none";
  };

  // ===========================================================================
  // Save button feedback
  // ===========================================================================
  document.getElementById("settings-form").addEventListener("submit", (e) => {
    // -- Convert radius / altitude fields back to stored units (km / metres) --
    // The backend always expects flight_radius in km and altitudes in metres,
    // so when the fields are currently displayed in imperial we convert in
    // place just before the browser submits the form.
    if (fieldsAreImperial) {
      const radiusInput = document.getElementById("flight_radius");
      const minAltInput = document.getElementById("flight_min_altitude");
      const maxAltInput = document.getElementById("flight_max_altitude");

      const radiusKm = miToKm(parseFloat(radiusInput.value) || RADIUS_BOUNDS.min);
      radiusInput.value = radiusKm;

      const minAltM = ftToM(parseFloat(minAltInput.value) || MIN_ALT_BOUNDS.min);
      minAltInput.value = minAltM;

      const maxAltM = ftToM(parseFloat(maxAltInput.value) || MAX_ALT_BOUNDS.min);
      maxAltInput.value = maxAltM;

      // The inputs now hold metric values; mark them as such so a subsequent
      // applyUnitToFields() (e.g. on a failed-submit restore) converts the
      // right way.
      fieldsAreImperial = false;
    }

    const weatherModeRadio = document.querySelector('input[name="weather_mode"]:checked');
    const weatherMode = weatherModeRadio ? weatherModeRadio.value : "0";
    const weatherKey = document.getElementById("weatherapi_key").value.trim();
    const weatherErr = document.getElementById("weather_key_error");
    if (weatherMode !== "0" && !weatherKey) {
      e.preventDefault();
      weatherErr.style.display = "block";
      document.getElementById("group-weather-data").scrollIntoView({ behavior: "smooth", block: "center" });
      const btn = document.getElementById("save-btn");
      btn.disabled = false;
      btn.innerHTML = "Save &amp; Restart";
      // Restore the display-unit values so the fields still show miles/feet.
      applyUnitToFields();
      return;
    }
    weatherErr.style.display = "none";
    const btn = document.getElementById("save-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Saving…';
  });
})();