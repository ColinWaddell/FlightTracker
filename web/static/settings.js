/* ===== FlightTracker settings page logic ===== */
/* Expects: window.FT_AIRPORTS (JSON object of airport codes → names) */
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
      callsignFields.style.display = isFr24    ? "block" : "none";
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

  // -- Simple map --
  const initLat = parseFloat(document.getElementById("flight_lat").value) || 55.87;
  const initLng = parseFloat(document.getElementById("flight_lng").value) || -4.25;
  const initRadius = parseFloat(document.getElementById("flight_radius").value) || 20;

  const map = L.map("map").setView([initLat, initLng], 10);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors", maxZoom: 18,
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
              map.setView(L.latLng(lat, lng), map.getZoom(), { animate: true });
              marker.setLatLng([lat, lng]);
              circle.setLatLng([lat, lng]);
              updateLocation(lat, lng);
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
    updateLocation(pos.lat, pos.lng);
  });

  map.on("click", e => { if (!mapLocked) updateLocation(e.latlng.lat, e.latlng.lng); });

  document.getElementById("lat_display").addEventListener("change", () => {
    updateLocation(parseFloat(document.getElementById("lat_display").value), parseFloat(document.getElementById("lng_display").value));
  });
  document.getElementById("lng_display").addEventListener("change", () => {
    updateLocation(parseFloat(document.getElementById("lat_display").value), parseFloat(document.getElementById("lng_display").value));
  });

  // -- Radius slider --
  document.getElementById("flight_radius").addEventListener("input", e => {
    const r = parseFloat(e.target.value);
    document.getElementById("radius_display").textContent = r;
    circle.setRadius(r * 1000);
    map.fitBounds(circle.getBounds(), { padding: [20, 20] });
  });

  // ===========================================================================
  // Advanced map - editable rectangle + draggable observer marker
  // ===========================================================================
  const advTlY = parseFloat(document.getElementById("flight_zone_tl_y").value);
  const advTlX = parseFloat(document.getElementById("flight_zone_tl_x").value);
  const advBrY = parseFloat(document.getElementById("flight_zone_br_y").value);
  const advBrX = parseFloat(document.getElementById("flight_zone_br_x").value);
  const advObsLat = parseFloat(document.getElementById("flight_observer_lat").value);
  const advObsLng = parseFloat(document.getElementById("flight_observer_lng").value);

  const advMap = L.map("map_advanced", { doubleClickZoom: false }).setView([advObsLat, advObsLng], 10);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors", maxZoom: 18,
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
    document.getElementById("flight_zone_tl_x").value = bounds.getWest().toFixed(6);
    document.getElementById("flight_zone_br_y").value = bounds.getSouth().toFixed(6);
    document.getElementById("flight_zone_br_x").value = bounds.getEast().toFixed(6);
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
    syncAdvMarker(pos.lat, pos.lng);
  });

  advMap.on("click", e => {
    if (!advMapLocked) {
      advMarker.setLatLng(e.latlng);
      syncAdvMarker(e.latlng.lat, e.latlng.lng);
    }
  });

  // Double-click: set observer + centre a 10 km box around the location
  advMap.on("dblclick", e => {
    if (advMapLocked) return;
    const lat = e.latlng.lat;
    const lng = e.latlng.lng;
    advMarker.setLatLng(e.latlng);
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
    const lng = parseFloat(document.getElementById("observer_lng_display").value);
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      advMarker.setLatLng([lat, lng]);
      syncAdvMarker(lat, lng);
    }
  });
  document.getElementById("observer_lng_display").addEventListener("change", () => {
    const lat = parseFloat(document.getElementById("observer_lat_display").value);
    const lng = parseFloat(document.getElementById("observer_lng_display").value);
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
    hint.textContent = AIRPORTS[code] ? AIRPORTS[code] : (code.length >= 3 ? "Unknown airport" : "");
  });

  // Trigger on load
  (function () {
    const code = document.getElementById("home_airport_code").value.toUpperCase();
    const hint = document.getElementById("airport_name_hint");
    if (AIRPORTS[code]) hint.textContent = AIRPORTS[code];
  })();

  // ===========================================================================
  // Save button feedback
  // ===========================================================================
  document.getElementById("settings-form").addEventListener("submit", (e) => {
    const weatherMode = document.querySelector('input[name="weather_mode"]:checked').value;
    const weatherKey = document.getElementById("weatherapi_key").value.trim();
    const weatherErr = document.getElementById("weather_key_error");
    if (weatherMode !== "0" && !weatherKey) {
      e.preventDefault();
      weatherErr.style.display = "block";
      document.getElementById("group-weather-data").scrollIntoView({ behavior: "smooth", block: "center" });
      const btn = document.getElementById("save-btn");
      btn.disabled = false;
      btn.innerHTML = "Save &amp; Restart";
      return;
    }
    weatherErr.style.display = "none";
    const btn = document.getElementById("save-btn");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Saving…';
  });
})();