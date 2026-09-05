/**
 * Reactive settings store.
 *
 * A single reactive object holds every form field.  Each field uses the
 * same name as the backend config key so the form can be submitted with
 * plain <input name="..."> elements (the backend already knows how to
 * parse them).  Components read and write `store.config.*` directly.
 */

import { reactive, computed, ref, watch } from "./vendor.js";

// ---------------------------------------------------------------------------
// Conversion constants (metric ↔ imperial)
// ---------------------------------------------------------------------------

export const FT_PER_M = 3.28084;
export const MI_PER_KM = 0.621371;

export const mToFt = (m) => m * FT_PER_M;
export const ftToM = (ft) => ft / FT_PER_M;
export const kmToMi = (km) => km * MI_PER_KM;
export const miToKm = (mi) => mi / MI_PER_KM;

// Slider / input bounds expressed in the *stored* (metric) unit.
export const RADIUS_BOUNDS = { min: 1, max: 100, step: 0.5 }; // km
export const MIN_ALT_BOUNDS = { min: 10, max: 20000, step: 10 }; // metres
export const MAX_ALT_BOUNDS = { min: 100, max: 40000, step: 100 }; // metres

// Cap on advanced brightness schedule rows (48 = every half hour).
export const MAX_SCHEDULE_ROWS = 48;

// ---------------------------------------------------------------------------
// Template reference data (single source of truth for the autocomplete)
// ---------------------------------------------------------------------------

export const TEMPLATE_FIELDS = [
  { name: "callsign", label: "Flight callsign (e.g. BAW123)", units: null },
  { name: "icao_callsign", label: "ICAO callsign", units: null },
  { name: "airline_icao", label: "Airline ICAO code", units: null },
  { name: "operator_icao", label: "Registered operator ICAO code (from Mode S hex)", units: null },
  { name: "owner", label: "Registered owner name (e.g. for private/training aircraft)", units: null },
  { name: "plane", label: "Aircraft make & model", units: null },
  { name: "registration", label: "Aircraft registration", units: null },
  { name: "origin", label: "Origin airport code", units: null },
  { name: "destination", label: "Destination airport code", units: null },
  { name: "origin_name", label: "Origin airport name", units: null },
  { name: "destination_name", label: "Destination airport name", units: null },
  { name: "origin_municipality", label: "Origin city", units: null },
  { name: "destination_municipality", label: "Destination city", units: null },
  { name: "origin_country", label: "Origin country", units: null },
  { name: "destination_country", label: "Destination country", units: null },
  { name: "altitude", label: "Altitude", units: "ft, m" },
  { name: "ground_speed", label: "Ground speed", units: "knots/kts, kmh/kph, mph" },
  { name: "heading", label: "Heading (degrees)", units: "- (use {symbol:degree} for °)" },
  { name: "vertical_speed", label: "Vertical speed", units: "fpm, ms" },
];

export const TEMPLATE_SYMBOLS = [
  { tag: "{symbol:altitude}", label: "Altitude icon" },
  { tag: "{symbol:speed}", label: "Speed icon" },
  { tag: "{symbol:heading}", label: "Heading/compass icon" },
  { tag: "{symbol:degree}", label: "Degree symbol" },
  { tag: "{symbol:origin_arrow}", label: "Origin direction arrow" },
  { tag: "{symbol:dest_arrow}", label: "Destination direction arrow" },
  { tag: "{heading_arrow}", label: "Arrow pointing in the plane's heading direction (N, NE, E, SE, S, SW, W, NW)" },
  { tag: "{heading_direction}", label: "Cardinal direction text (N, NE, E, SE, S, SW, W, NW) based on the plane's heading" },
];

// ---------------------------------------------------------------------------
// Sidebar navigation definition
// ---------------------------------------------------------------------------

export const SIDEBAR_GROUPS = [
  {
    title: "Sky Monitoring",
    icon: "bi-rocket-takeoff-pin",
    route: "/sky-monitoring",
    items: [
      { section: "group-sky-monitoring", icon: "bi-geo-alt", label: "Location" },
      { section: "group-airport-display", icon: "bi-airplane", label: "Airport Display" },
      { section: "group-airline-info", icon: "bi-ticket-perforated", label: "Airline Info" },
      { section: "group-plane-info", icon: "bi-info-circle", label: "Plane Details" },
      { section: "group-satellite", icon: "bi-rocket-takeoff", label: "Satellite Tracking" },
    ],
  },
  {
    title: "Data Source",
    icon: "bi-hdd-network",
    route: "/data-source",
    items: [
      { section: "group-lookup-priority", icon: "bi-sort-numeric-down", label: "Data Manager" },
      { section: "group-provider-config", icon: "bi-sliders", label: "Provider Settings" },
      { section: "group-weather-data", icon: "bi-cloud-sun", label: "Weather Data" },
    ],
  },
  {
    title: "Default Screen",
    icon: "bi-house",
    route: "/default-screen",
    items: [
      { section: "group-theme", icon: "bi-palette", label: "Theme" },
    ],
  },
  {
    title: "System",
    icon: "bi-cpu",
    route: "/hardware",
    items: [
      { section: "group-display", icon: "bi-pip", label: "Display" },
      { section: "group-hardware", icon: "bi-motherboard", label: "Hardware" },
      { section: "group-web-interface", icon: "bi-filetype-html", label: "Web Interface" },
      { section: "group-defaults", icon: "bi-rulers", label: "Defaults" },
    ],
  },
  {
    title: "Admin",
    icon: "bi-shield-lock",
    route: "/admin",
    items: [
      { section: "group-logging", icon: "bi-terminal", label: "Logging" },
      { section: "group-clear-cache", icon: "bi-database", label: "Cache" },
      { section: "group-backup", icon: "bi-file-earmark-arrow-down", label: "Backup" },
      { section: "group-password", icon: "bi-key", label: "Change Password" },
      { section: "group-version", icon: "bi-info-circle", label: "Version" },
      { section: "group-help", icon: "bi-question-circle", label: "Help & Support" },
    ],
  },
];

// ---------------------------------------------------------------------------
// Reactive store
// ---------------------------------------------------------------------------

/**
 * Create the reactive store.
 *
 * @param {object} initialConfig  - cfg dict injected by Jinja (window.FT_CONFIG)
 * @param {object} pageData       - extra page data (airports, version, etc.)
 * @returns {object} store with `config`, `ui`, and computed helpers
 */
export function createStore(initialConfig, pageData) {
  const config = reactive({ ...initialConfig });

  // UI-only state (not submitted to the backend)
  const ui = reactive({
    saving: false,
    weatherKeyError: false,
    templateErrors: pageData.templateErrors || [],
    serverError: pageData.error || null,
    importFailed: pageData.importFailed || false,
    airports: pageData.airports || {},
    currentVersion: pageData.currentVersion || "",
    inSchedule: pageData.inSchedule || false,
    scheduleWindow: pageData.scheduleWindow || [null, null],
    csrfToken: pageData.csrfToken || "",
    staticUrls: pageData.staticUrls || {},
    symbolImages: pageData.symbolImages || {},
    urls: pageData.urls || {},
    providersMeta: pageData.providersMeta || [],
    maskToken: pageData.maskToken || "**********",
  });

  // Provider priority lists - reactive copies of the configured order.
  // The Providers page reorders/toggles these and serialises them into
  // hidden JSON inputs at submit time.
  const flightProvidersOrder = reactive(
    (pageData.flightProvidersOrder || []).map((e) => ({ ...e }))
  );
  const routeProvidersOrder = reactive(
    (pageData.routeProvidersOrder || []).map((e) => ({ ...e }))
  );

  // Advanced brightness schedule - reactive rows of {id, time, brightness}.
  // The Hardware page edits these and serialises them into a hidden JSON
  // input at submit time.  `id` is a stable row key so inputs keep focus
  // when the list is re-sorted; it is never submitted.
  let scheduleRowId = 0;
  const screenScheduleAdvanced = reactive(
    (config.screen_schedule_advanced || []).map((e) => ({
      id: ++scheduleRowId,
      time: e.time || "",
      brightness: Number(e.brightness ?? 0),
    }))
  );

  const timeToMinutes = (t) => {
    const m = /^(\d{1,2}):(\d{2})$/.exec(t || "");
    if (!m) return null;
    const h = Number(m[1]);
    const min = Number(m[2]);
    if (h > 23 || min > 59) return null;
    return h * 60 + min;
  };

  const minutesToTime = (mins) =>
    `${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;

  const addScheduleRow = () => {
    if (screenScheduleAdvanced.length >= MAX_SCHEDULE_ROWS) return;
    // Pick the first free half-hour slot so a new row never collides.
    const taken = new Set(
      screenScheduleAdvanced
        .map((r) => timeToMinutes(r.time))
        .filter((m) => m !== null)
    );
    let slot = 0;
    while (taken.has(slot) && slot < 24 * 60) slot += 30;
    screenScheduleAdvanced.push({
      id: ++scheduleRowId,
      time: minutesToTime(slot % 24 * 60),
      brightness: 3,
    });
  };

  const removeScheduleRow = (id) => {
    const index = screenScheduleAdvanced.findIndex((r) => r.id === id);
    if (index !== -1) screenScheduleAdvanced.splice(index, 1);
  };

  // Stable sort by time; called when a row's time input changes so the
  // table always reads in chronological order.
  const resortSchedule = () => {
    const rows = screenScheduleAdvanced
      .map((row, index) => ({ row, index, mins: timeToMinutes(row.time) }))
      .sort((a, b) => {
        // Rows without a valid time keep their current position.
        if (a.mins === null && b.mins === null) return a.index - b.index;
        if (a.mins === null) return 1;
        if (b.mins === null) return -1;
        return a.mins - b.mins || a.index - b.index;
      })
      .map((e) => e.row);
    screenScheduleAdvanced.splice(0, screenScheduleAdvanced.length, ...rows);
  };

  const scheduleRowValid = (row) => {
    const mins = timeToMinutes(row.time);
    if (mins === null) return false;
    return !screenScheduleAdvanced.some(
      (other) => other.id !== row.id && timeToMinutes(other.time) === mins
    );
  };

  // Serialise the valid rows into the hidden-input payload.  Invalid rows
  // (empty/duplicate times) are excluded so the backend never sees them.
  const scheduleAdvancedJson = () =>
    JSON.stringify(
      screenScheduleAdvanced
        .filter((row) => scheduleRowValid(row))
        .map((row) => ({ time: row.time, brightness: row.brightness }))
    );

  // Format an "HH:MM" string honouring the 12/24hr clock setting.
  const formatTime = (t) => {
    const mins = timeToMinutes(t);
    if (mins === null) return "--:--";
    if (config.clock_24hr) return minutesToTime(mins);
    const h24 = Math.floor(mins / 60);
    const suffix = h24 < 12 ? "AM" : "PM";
    const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
    return `${h12}:${String(mins % 60).padStart(2, "0")} ${suffix}`;
  };

  const scheduleAdvancedPreview = computed(() => {
    const rows = screenScheduleAdvanced
      .filter((row) => scheduleRowValid(row))
      .map((row) => `${formatTime(row.time)} \u2192 ${row.brightness}`);
    return rows.length ? rows.join(", ") : "";
  });

  // -- Computed helpers --------------------------------------------------

  const isImperial = computed(() => config.height_unit === "ft");

  const isAdvancedLocation = computed(
    () => config.flight_location_mode === "advanced",
  );

  const isAdvancedBrightness = computed(
    () => config.brightness_mode === "advanced",
  );

  const noradIdsText = computed({
    get: () => (config.satellite_norad_ids || []).join("\n"),
    set: (text) => {
      config.satellite_norad_ids = text
        .split("\n")
        .map((n) => n.trim())
        .filter((n) => n !== "");
    },
  });

  const homeAirportHint = computed(() => {
    const code = (config.home_airport_code || "").toUpperCase();
    if (code.length < 3) return "";
    return ui.airports[code]?.name ?? "Unknown airport";
  });

  const braceCounts = computed(() => {
    const val = config.details_custom_template || "";
    return {
      opens: (val.match(/\{/g) || []).length,
      closes: (val.match(/\}/g) || []).length,
    };
  });

  const braceBalanced = computed(() => braceCounts.value.opens === braceCounts.value.closes);

  const braceMessage = computed(() => {
    const { opens, closes } = braceCounts.value;
    if (opens === closes) return "";
    return `Unbalanced braces: ${opens} opening { but ${closes} closing }.`;
  });

  // -- Unit conversion helpers ------------------------------------------
  // The backend stores radius in km and altitudes in metres.  When the
  // display unit is imperial we show miles/feet.  Each display field
  // uses a ref + watcher pattern: the ref holds the display value so
  // typing doesn't fight a round-trip conversion, and a watcher keeps
  // the stored config (always metric) in sync.

  // -- Radius display value -------------------------------------------
  // Same ref+watcher pattern as altitude: the ref holds the display
  // value so typing doesn't fight a round-trip conversion.  The stored
  // config (always km) is kept in sync via a watcher.

  const displayRadius = ref(
    isImperial.value
      ? kmToMi(config.flight_radius)
      : config.flight_radius,
  );

  watch(isImperial, (imperial, wasImperial) => {
    if (imperial === wasImperial) return;
    if (imperial) {
      displayRadius.value = kmToMi(config.flight_radius);
    } else {
      displayRadius.value = miToKm(displayRadius.value);
    }
  });

  watch([displayRadius, isImperial], () => {
    config.flight_radius = isImperial.value
      ? miToKm(displayRadius.value)
      : displayRadius.value;
  });

  // -- Altitude display values -----------------------------------------
  // We keep separate refs for the displayed altitude values so that
  // typing into the input doesn't fight with a round-trip conversion
  // (type 5000 ft -> store 1524 m -> re-display 4999 ft).  The refs
  // are initialised from the stored config, and a watcher converts
  // them when the unit changes.  The stored config is updated via
  // a separate watcher so the hidden inputs always have metric values.

  const displayMinAlt = ref(
    isImperial.value
      ? Math.round(mToFt(config.flight_min_altitude))
      : config.flight_min_altitude,
  );
  const displayMaxAlt = ref(
    isImperial.value
      ? Math.round(mToFt(config.flight_max_altitude))
      : config.flight_max_altitude,
  );

  // When the unit changes, convert the displayed values to the new unit.
  watch(isImperial, (imperial, wasImperial) => {
    if (imperial === wasImperial) return;
    if (imperial) {
      displayMinAlt.value = Math.round(mToFt(config.flight_min_altitude));
      displayMaxAlt.value = Math.round(mToFt(config.flight_max_altitude));
    } else {
      displayMinAlt.value = Math.round(ftToM(displayMinAlt.value));
      displayMaxAlt.value = Math.round(ftToM(displayMaxAlt.value));
    }
  });

  // Keep the stored config in sync with the display values (metric).
  watch([displayMinAlt, isImperial], () => {
    config.flight_min_altitude = isImperial.value
      ? Math.round(ftToM(displayMinAlt.value))
      : displayMinAlt.value;
  });
  watch([displayMaxAlt, isImperial], () => {
    config.flight_max_altitude = isImperial.value
      ? Math.round(ftToM(displayMaxAlt.value))
      : displayMaxAlt.value;
  });

  // Slider bounds in the *display* unit.  Steps are clean whole/half
  // numbers in the display unit, not raw conversions of the metric step.
  const radiusBoundsDisplay = computed(() =>
    isImperial.value
      ? {
          min: RADIUS_BOUNDS.min * MI_PER_KM,
          max: RADIUS_BOUNDS.max * MI_PER_KM,
          step: 0.5,
        }
      : RADIUS_BOUNDS,
  );

  const minAltBoundsDisplay = computed(() =>
    isImperial.value
      ? {
          min: Math.round(MIN_ALT_BOUNDS.min * FT_PER_M),
          max: Math.round(MIN_ALT_BOUNDS.max * FT_PER_M),
          step: 10,
        }
      : MIN_ALT_BOUNDS,
  );

  const maxAltBoundsDisplay = computed(() =>
    isImperial.value
      ? {
          min: Math.round(MAX_ALT_BOUNDS.min * FT_PER_M),
          max: Math.round(MAX_ALT_BOUNDS.max * FT_PER_M),
          step: 100,
        }
      : MAX_ALT_BOUNDS,
  );

  const altitudeUnitLabel = computed(() => (isImperial.value ? "ft" : "m"));
  const radiusUnitLabel = computed(() => (isImperial.value ? "mi" : "km"));
  const altitudeHelpExample = computed(() =>
    isImperial.value ? "30ft" : "10m",
  );

  return reactive({
    config,
    ui,
    isImperial,
    isAdvancedLocation,
    isAdvancedBrightness,
    noradIdsText,
    homeAirportHint,
    braceBalanced,
    braceMessage,
    displayRadius,
    displayMinAlt,
    displayMaxAlt,
    radiusBoundsDisplay,
    minAltBoundsDisplay,
    maxAltBoundsDisplay,
    altitudeUnitLabel,
    radiusUnitLabel,
    altitudeHelpExample,
    flightProvidersOrder,
    routeProvidersOrder,
    screenScheduleAdvanced,
    addScheduleRow,
    removeScheduleRow,
    resortSchedule,
    scheduleAdvancedJson,
    scheduleAdvancedPreview,
    formatTime,
  });
}