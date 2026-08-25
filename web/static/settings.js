/* ===== FlightTracker settings page ===================================
 *
 * One Vue 3 app (Options API) owns the entire settings UI.
 *
 * External dependencies expected on window before this file loads:
 *   Vue, VueRouter  – loaded from CDN
 *   L               – Leaflet + Geoman plugin
 *   FT_AIRPORTS     – { ICAO: { name, … }, … }  (set by the template)
 *   FT_CONFIG       – initial server-rendered config object (set by template)
 *
 * The form still submits as a standard POST.  Vue manages every piece of
 * conditional display and validates/converts units before submission.
 * ===================================================================== */

'use strict'

// ─── Unit conversion ──────────────────────────────────────────────────────────

const FT_PER_M  = 3.28084
const MI_PER_KM = 0.621371

const mToFt  = m   => m  * FT_PER_M
const ftToM  = ft  => ft / FT_PER_M
const kmToMi = km  => km * MI_PER_KM
const miToKm = mi  => mi / MI_PER_KM

// Normalise any longitude to [-180, 180) so values never drift onto a
// repeated world-copy when the user pans past the antimeridian.
const wrapLng = lng => ((lng + 180) % 360 + 360) % 360 - 180

// Slider bounds in the stored (metric) unit.
const RADIUS_BOUNDS  = { min: 1,   max: 100,   step: 0.5  }  // km
const MIN_ALT_BOUNDS = { min: 10,  max: 20000, step: 10   }  // metres
const MAX_ALT_BOUNDS = { min: 100, max: 40000, step: 100  }  // metres

// ─── Leaflet constants ────────────────────────────────────────────────────────

const WORLD_BOUNDS = L.latLngBounds([-90, -180], [90, 180])

const SVG_LOCKED   = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 1a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2h-1V6a5 5 0 0 0-5-5Zm-3 8V6a3 3 0 1 1 6 0v3H9Z"/></svg>'
const SVG_UNLOCKED = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M17 9V7a5 5 0 0 0-9.9-1H9a3 3 0 0 1 6 0v3H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2h-1Z"/></svg>'
const SVG_LOCATION = '<svg viewBox="0 0 24 24"><path d="M12 0c-4.198 0-8 3.403-8 7.602 0 4.198 3.469 9.21 8 16.398 4.531-7.188 8-12.2 8-16.398 0-4.199-3.801-7.602-8-7.602zm0 11c-1.657 0-3-1.343-3-3s1.343-3 3-3 3 1.343 3 3-1.343 3-3 3z"/></svg>'
const SVG_OBS_MARKER = '<svg viewBox="0 0 24 24" width="28" height="28" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,.4))"><path d="M12 0c-4.198 0-8 3.403-8 7.602 0 4.198 3.469 9.21 8 16.398 4.531-7.188 8-12.2 8-16.398 0-4.199-3.801-7.602-8-7.602zm0 11c-1.657 0-3-1.343-3-3s1.343-3 3-3 3 1.343 3 3-1.343 3-3 3z" fill="#dc3545"/></svg>'

// ─── Router ───────────────────────────────────────────────────────────────────
// All pages stay mounted in the DOM (needed for traditional form POST),
// so route components are no-op placeholders.  Page visibility is handled
// with v-show driven by `currentPage`.

const { createApp } = Vue
const { createRouter, createWebHashHistory } = VueRouter

const PAGES = ['sky-monitoring', 'data-source', 'default-screen', 'hardware', 'admin']

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/sky-monitoring' },
    ...PAGES.map(p => ({ path: `/${p}`, component: { template: '<div />' } })),
  ],
  linkActiveClass: '',
  linkExactActiveClass: '',
})

// ─── App ──────────────────────────────────────────────────────────────────────

createApp({

  // ── Reactive state ──────────────────────────────────────────────────────────

  data() {
    const cfg = window.FT_CONFIG || {}

    // When height_unit is already 'ft' on load the radius display should
    // start in miles, not kilometres.
    const storedRadius = cfg.flight_radius ?? 20
    const initialUnit  = cfg.height_unit || 'm'
    const initialRadiusDisplay = initialUnit === 'ft' ? kmToMi(storedRadius) : storedRadius

    return {
      // Navigation
      currentPage:          'sky-monitoring',
      activeSidebarSection: null,
      pendingSection:       null,

      // Sky Monitoring
      locationMode: cfg.flight_location_mode || 'simple',

      // Data source
      dataSource: cfg.data_source || 'fr24',

      // Satellite tracking
      satelliteEnabled:        Boolean(cfg.satellite_tracking_enabled),
      satelliteTimeoutEnabled: Boolean(cfg.satellite_timeout_enabled),

      // Airport display (value kept as string – HTML radio values are strings)
      airportDisplayStyle: String(cfg.airport_display_style ?? 0),
      airportCode:         (cfg.home_airport_code || '').toUpperCase(),

      // Plane details
      planeDetailsMode: String(cfg.details ?? 0),
      customTemplate:   cfg.details_custom_template || '',

      // Autocomplete state for the custom template textarea
      autocomplete: {
        visible:       false,
        items:         [],
        selectedIndex: -1,
        position:      { left: 0, top: 0 },
        tagNames:      [],   // populated in mounted()
      },

      // Weather
      weatherMode:    String(cfg.weather_mode ?? 0),
      weatherKeyError: false,

      // Idle screen theme
      idleScreenTheme: cfg.idle_screen_theme || 'classic',

      // Brightness schedule
      scheduleEnabled: Boolean(cfg.screen_schedule_enabled),
      scheduleAuto:    Boolean(cfg.screen_schedule_auto),

      // Hardware
      loadingIndicator: cfg.loading_indicator || 'none',

      // Units
      heightUnit:       initialUnit,
      fieldsAreImperial: false,   // tracks whether alt/radius inputs are in imperial

      // Map interaction
      simpleMapLocked: true,
      advMapLocked:    true,

      // Slider display values (shown in labels alongside the inputs)
      radiusDisplay:   initialRadiusDisplay,
      brightness:      cfg.screen_brightness          ?? 3,
      nightBrightness: cfg.screen_schedule_brightness ?? 1,

      // Form save state
      isSaving: false,
    }
  },

  // ── Derived state ────────────────────────────────────────────────────────────

  computed: {
    // Location mode
    showSimpleTracking()   { return this.locationMode !== 'advanced' },
    showAdvancedTracking() { return this.locationMode === 'advanced' },

    // Data source conditional sections
    showTar1090Fields() { return this.dataSource === 'tar1090' },
    showOsnFields()     { return this.dataSource === 'osn' },
    showFr24Warning()   { return this.dataSource === 'fr24' },

    // Airport display
    showHomeAirportFields() { return this.airportDisplayStyle === '0' },

    airportNameHint() {
      const airports = window.FT_AIRPORTS || {}
      return airports[this.airportCode]?.name
        ?? (this.airportCode.length >= 3 ? 'Unknown airport' : '')
    },

    // Plane details
    showCustomTemplatePanel() { return this.planeDetailsMode === '2' },

    braceError() {
      const opens  = (this.customTemplate.match(/\{/g) || []).length
      const closes = (this.customTemplate.match(/\}/g) || []).length
      if (opens === closes) return null
      return `Unbalanced braces: ${opens} opening { but ${closes} closing }.`
    },

    // Satellite
    showSatelliteFields()        { return this.satelliteEnabled },
    showSatelliteTimeoutFields() { return this.satelliteTimeoutEnabled },

    // Weather / idle theme
    showRainSensitivity() { return this.weatherMode === '2' },
    showClassicTheme()    { return this.idleScreenTheme === 'classic' },
    showForecastTheme()   { return this.idleScreenTheme === 'forecast' },
    showConditionsTheme() { return this.idleScreenTheme === 'conditions' },

    // Schedule
    showScheduleFields() { return this.scheduleEnabled },
    showManualTimes()    { return this.scheduleEnabled && !this.scheduleAuto },

    // Hardware
    showLedPinField() { return this.loadingIndicator === 'gpio' },

    // Units
    isImperial()     { return this.heightUnit === 'ft' },
    radiusUnitLabel(){ return this.isImperial ? 'mi' : 'km' },
    altUnitLabel()   { return this.isImperial ? 'ft' : 'm' },
    altHelpExample() { return this.isImperial ? '30ft' : '10m' },
  },

  // ── Side effects ─────────────────────────────────────────────────────────────

  watch: {
    '$route'(to) {
      const page = to.path.replace(/^\//, '') || 'sky-monitoring'
      this.currentPage = page

      if (this.pendingSection) {
        const section       = this.pendingSection
        this.pendingSection = null
        this.activeSidebarSection = section
        this.$nextTick(() => {
          const el = document.getElementById(section)
          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        })
      } else {
        this.activeSidebarSection = null
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }

      // Leaflet needs to recalculate tile layout after its container is shown.
      if (page === 'sky-monitoring') {
        this.$nextTick(() => setTimeout(() => this.refreshMapSizes(), 100))
      }
    },

    locationMode() {
      // Tile layout breaks when maps are shown after being hidden.
      this.$nextTick(() => setTimeout(() => this.refreshMapSizes(), 50))
    },

    heightUnit() {
      this.applyUnitToFields()
    },

    airportCode(val) {
      // Enforce uppercase; the watch only fires again if the value really changed.
      const upper = val.toUpperCase()
      if (upper !== val) this.airportCode = upper
    },
  },

  // ── Lifecycle ─────────────────────────────────────────────────────────────────

  mounted() {
    const initial = this.$route.path.replace(/^\//, '')
    if (initial) this.currentPage = initial

    this.initSimpleMap()
    this.initAdvancedMap()
    this.applyUnitToFields()
    this.collectTemplateTagNames()
  },

  // ── Methods ───────────────────────────────────────────────────────────────────

  methods: {

    // ── Sidebar navigation ─────────────────────────────────────────────────────

    // Called on every sidebar router-link @click.
    // If already on the target page, scroll immediately.
    // If navigating to a different page, the route watcher scrolls after transition.
    onSidebarLinkClick(targetPage, section) {
      this.pendingSection = section
      const current = this.$route.path.replace(/^\//, '')
      if (current === targetPage) {
        this.activeSidebarSection = section
        const el = document.getElementById(section)
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        this.pendingSection = null
      }
    },

    isSectionActive(section) {
      return this.activeSidebarSection === section
    },

    // ── Simple (circle) map ───────────────────────────────────────────────────

    initSimpleMap() {
      const lat    = parseFloat(document.getElementById('flight_lat').value)    || 55.87
      const lng    = parseFloat(document.getElementById('flight_lng').value)    || -4.25
      const radius = parseFloat(document.getElementById('flight_radius').value) || 20

      this._map = L.map('map', {
        worldCopyJump: true, maxBounds: WORLD_BOUNDS, maxBoundsViscosity: 1.0,
      }).setView([lat, lng], 10)

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors', maxZoom: 18, noWrap: true,
      }).addTo(this._map)

      this._marker = L.marker([lat, lng], { draggable: true }).addTo(this._map)
      this._circle = L.circle([lat, lng], {
        radius: radius * 1000, color: '#0d6efd', fillOpacity: 0.1,
      }).addTo(this._map)

      this._map.fitBounds(this._circle.getBounds(), { padding: [20, 20] })
      this._map.addControl(this.makeLockControl(locked => this.setSimpleMapLocked(locked)))
      this._map.addControl(this.makeCurrentLocationControl())
      this.setSimpleMapLocked(true)

      this._marker.on('dragend', e => {
        const pos = e.target.getLatLng()
        this.updateSimpleLocation(pos.lat, wrapLng(pos.lng))
      })
      this._map.on('click', e => {
        if (!this.simpleMapLocked) {
          this.updateSimpleLocation(e.latlng.lat, wrapLng(e.latlng.lng))
        }
      })

      // Leaflet needs invalidateSize() if its container was hidden on load.
      if (this.locationMode !== 'advanced') {
        setTimeout(() => {
          this._map.invalidateSize()
          this._map.fitBounds(this._circle.getBounds(), { padding: [20, 20] })
        }, 100)
      }
    },

    updateSimpleLocation(lat, lng) {
      document.getElementById('flight_lat').value  = lat.toFixed(6)
      document.getElementById('flight_lng').value  = lng.toFixed(6)
      document.getElementById('lat_display').value = lat.toFixed(6)
      document.getElementById('lng_display').value = lng.toFixed(6)
      this._marker.setLatLng([lat, lng])
      this._circle.setLatLng([lat, lng])
    },

    onLatLngDisplayChange() {
      const lat = parseFloat(document.getElementById('lat_display').value)
      const lng = wrapLng(parseFloat(document.getElementById('lng_display').value))
      if (Number.isFinite(lat) && Number.isFinite(lng)) {
        this.updateSimpleLocation(lat, lng)
      }
    },

    onRadiusInput(e) {
      const r = parseFloat(e.target.value)
      this.radiusDisplay = r
      const radiusKm = this.isImperial ? miToKm(r) : r
      this._circle.setRadius(radiusKm * 1000)
      this._map.fitBounds(this._circle.getBounds(), { padding: [20, 20] })
    },

    setSimpleMapLocked(locked) {
      this.simpleMapLocked = locked
      this.toggleMapInteraction(this._map, this._marker, locked)
      document.getElementById('lat_display').disabled = locked
      document.getElementById('lng_display').disabled = locked
      if (this._locationButton) {
        this._locationButton.disabled     = locked
        this._locationButton.style.opacity = locked ? '0.45' : ''
        this._locationButton.title = locked
          ? 'Unlock the map to use current location'
          : 'Use my current location'
      }
    },

    // ── Advanced (bounding-box) map ────────────────────────────────────────────

    initAdvancedMap() {
      const tlY    = parseFloat(document.getElementById('flight_zone_tl_y').value)
      const tlX    = parseFloat(document.getElementById('flight_zone_tl_x').value)
      const brY    = parseFloat(document.getElementById('flight_zone_br_y').value)
      const brX    = parseFloat(document.getElementById('flight_zone_br_x').value)
      const obsLat = parseFloat(document.getElementById('flight_observer_lat').value)
      const obsLng = parseFloat(document.getElementById('flight_observer_lng').value)

      this._advMap = L.map('map_advanced', {
        doubleClickZoom: false, worldCopyJump: true,
        maxBounds: WORLD_BOUNDS, maxBoundsViscosity: 1.0,
      }).setView([obsLat, obsLng], 10)

      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors', maxZoom: 18, noWrap: true,
      }).addTo(this._advMap)

      this._advRect = L.rectangle(
        [[tlY, tlX], [brY, brX]],
        { color: '#198754', weight: 2, fillOpacity: 0.1 }
      ).addTo(this._advMap)

      const obsIcon = L.divIcon({
        className: '',
        html: SVG_OBS_MARKER,
        iconSize: [28, 28],
        iconAnchor: [14, 28],
      })
      this._advMarker = L.marker([obsLat, obsLng], {
        icon: obsIcon, draggable: true,
      }).addTo(this._advMap)

      this._advMap.fitBounds(this._advRect.getBounds(), { padding: [20, 20] })
      this.enableAdvRectEditing()
      this._advMap.addControl(this.makeLockControl(locked => this.setAdvMapLocked(locked)))
      this.setAdvMapLocked(true)

      this._advMarker.on('dragend', e => {
        const pos = e.target.getLatLng()
        this.syncAdvMarker(pos.lat, wrapLng(pos.lng))
      })

      this._advMap.on('click', e => {
        if (!this.advMapLocked) {
          const lng = wrapLng(e.latlng.lng)
          this._advMarker.setLatLng([e.latlng.lat, lng])
          this.syncAdvMarker(e.latlng.lat, lng)
        }
      })

      // Double-click: place observer and centre a fresh 10 km search box.
      this._advMap.on('dblclick', e => {
        if (this.advMapLocked) return
        const lat = e.latlng.lat
        const lng = wrapLng(e.latlng.lng)
        this._advMarker.setLatLng([lat, lng])
        this.syncAdvMarker(lat, lng)
        this.recenterAdvRect(lat, lng)
      })

      if (this.locationMode === 'advanced') {
        setTimeout(() => {
          this._advMap.invalidateSize()
          this._advMap.fitBounds(this._advRect.getBounds(), { padding: [20, 20] })
        }, 100)
      }
    },

    enableAdvRectEditing() {
      this._advMap.pm.addControls({
        position: 'topleft',
        drawRectangle: false, drawPolygon: false, drawCircle: false,
        drawPolyline: false,  drawCircleMarker: false, drawMarker: false,
        drawText: false,      cutPolygon: false, rotateMode: false,
        removalMode: false,   editMode: false,
      })
      // Remove the Geoman toolbar – we only need the programmatic API.
      const toolbar = this._advMap.pm.getControlContainer?.()
      if (toolbar) toolbar.remove()

      this._advRect.pm.enable({ snappable: false, preventIntersection: false })
      const sync = () => this.syncAdvRect()
      this._advRect.on('pm:edit',    sync)
      this._advRect.on('pm:dragend', sync)
      this._advRect.on('pm:resize',  sync)
    },

    syncAdvRect() {
      const b = this._advRect.getBounds()
      document.getElementById('flight_zone_tl_y').value = b.getNorth().toFixed(6)
      document.getElementById('flight_zone_tl_x').value = wrapLng(b.getWest()).toFixed(6)
      document.getElementById('flight_zone_br_y').value = b.getSouth().toFixed(6)
      document.getElementById('flight_zone_br_x').value = wrapLng(b.getEast()).toFixed(6)
    },

    syncAdvMarker(lat, lng) {
      document.getElementById('flight_observer_lat').value  = lat.toFixed(6)
      document.getElementById('flight_observer_lng').value  = lng.toFixed(6)
      document.getElementById('observer_lat_display').value = lat.toFixed(6)
      document.getElementById('observer_lng_display').value = lng.toFixed(6)
    },

    onObserverCoordChange() {
      const lat = parseFloat(document.getElementById('observer_lat_display').value)
      const lng = wrapLng(parseFloat(document.getElementById('observer_lng_display').value))
      if (Number.isFinite(lat) && Number.isFinite(lng)) {
        this._advMarker.setLatLng([lat, lng])
        this.syncAdvMarker(lat, lng)
      }
    },

    // Replace the editable rectangle with a fresh 10 km box centred on lat/lng.
    recenterAdvRect(lat, lng) {
      const boxLatDeg = 10 / 111.0
      const boxLngDeg = 10 / (111.0 * Math.cos(lat * Math.PI / 180))
      this._advRect.pm.disable()
      this._advMap.removeLayer(this._advRect)
      this._advRect = L.rectangle(
        [[lat + boxLatDeg, lng - boxLngDeg], [lat - boxLatDeg, lng + boxLngDeg]],
        { color: '#198754', weight: 2, fillOpacity: 0.1 }
      ).addTo(this._advMap)
      this.enableAdvRectEditing()
      this.syncAdvRect()
      this._advMap.fitBounds(this._advRect.getBounds(), { padding: [20, 20] })
    },

    setAdvMapLocked(locked) {
      this.advMapLocked = locked
      this.toggleMapInteraction(this._advMap, this._advMarker, locked)
      document.getElementById('observer_lat_display').disabled = locked
      document.getElementById('observer_lng_display').disabled = locked
      if (locked) {
        this._advRect.pm.disable()
      } else {
        this._advRect.pm.enable({ snappable: false, preventIntersection: false })
      }
    },

    // ── Shared Leaflet helpers ─────────────────────────────────────────────────

    toggleMapInteraction(leafletMap, leafletMarker, locked) {
      const action = locked ? 'disable' : 'enable'
      ;['dragging', 'scrollWheelZoom', 'touchZoom', 'doubleClickZoom', 'boxZoom', 'keyboard']
        .forEach(h => leafletMap[h]?.[action]?.())
      leafletMap.tap?.[action]?.()
      leafletMarker.dragging[action]()
    },

    refreshMapSizes() {
      if (this._map && !this.showAdvancedTracking) {
        this._map.invalidateSize()
        this._map.fitBounds(this._circle.getBounds(), { padding: [20, 20] })
      }
      if (this._advMap && this.showAdvancedTracking) {
        this._advMap.invalidateSize()
        this._advMap.fitBounds(this._advRect.getBounds(), { padding: [20, 20] })
      }
    },

    // Returns a new Leaflet control class whose button calls onToggle(locked).
    makeLockControl(onToggle) {
      return L.Control.extend({
        options: { position: 'topleft' },
        onAdd() {
          const container = L.DomUtil.create('div', 'leaflet-control leaflet-bar map-lock-control')
          const button    = L.DomUtil.create('button', '', container)
          button.type = 'button'
          button.setAttribute('aria-label', 'Toggle map lock')
          let locked = true

          const render = () => {
            button.innerHTML = locked ? SVG_LOCKED : SVG_UNLOCKED
            button.setAttribute('aria-pressed', String(locked))
            button.title = locked
              ? 'Map locked (click to unlock)'
              : 'Map unlocked (click to lock)'
          }

          L.DomEvent.disableClickPropagation(container)
          L.DomEvent.disableScrollPropagation(container)
          L.DomEvent.on(button, 'click', e => {
            L.DomEvent.stop(e)
            locked = !locked
            onToggle(locked)
            render()
          })
          render()
          return container
        },
      })
    },

    makeCurrentLocationControl() {
      const self = this
      return L.Control.extend({
        options: { position: 'topleft' },
        onAdd() {
          const container = L.DomUtil.create('div', 'leaflet-control leaflet-bar map-lock-control')
          const button    = L.DomUtil.create('button', '', container)
          button.type = 'button'
          button.setAttribute('aria-label', 'Use my current location')
          button.innerHTML = SVG_LOCATION
          self._locationButton = button

          L.DomEvent.disableClickPropagation(container)
          L.DomEvent.disableScrollPropagation(container)
          L.DomEvent.on(button, 'click', e => {
            L.DomEvent.stop(e)
            if (self.simpleMapLocked || !('geolocation' in navigator)) return
            button.disabled     = true
            button.style.opacity = '0.6'
            navigator.geolocation.getCurrentPosition(
              pos => {
                const lat = pos.coords.latitude
                const lng = wrapLng(pos.coords.longitude)
                if (Number.isFinite(lat) && Number.isFinite(lng)) {
                  self._map.setView(L.latLng(lat, lng), self._map.getZoom(), { animate: true })
                  self.updateSimpleLocation(lat, lng)
                }
                button.disabled     = false
                button.style.opacity = ''
              },
              () => { button.disabled = false; button.style.opacity = '' },
              { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            )
          })
          return container
        },
      })
    },

    // ── Unit conversion ────────────────────────────────────────────────────────

    applyUnitToFields() {
      const imperial    = this.isImperial
      const radiusInput = document.getElementById('flight_radius')
      const minAltInput = document.getElementById('flight_min_altitude')
      const maxAltInput = document.getElementById('flight_max_altitude')

      if (imperial === this.fieldsAreImperial) {
        // Unit unchanged – just refresh the radius display label.
        this.radiusDisplay = parseFloat(radiusInput.value) || RADIUS_BOUNDS.min
        return
      }

      // Radius: km ↔ miles
      const curRadius = parseFloat(radiusInput.value) || RADIUS_BOUNDS.min
      const newRadius = imperial ? kmToMi(curRadius) : miToKm(curRadius)
      radiusInput.min   = imperial ? (RADIUS_BOUNDS.min  * MI_PER_KM).toFixed(3) : RADIUS_BOUNDS.min
      radiusInput.max   = imperial ? (RADIUS_BOUNDS.max  * MI_PER_KM).toFixed(3) : RADIUS_BOUNDS.max
      radiusInput.step  = imperial ? (RADIUS_BOUNDS.step * MI_PER_KM).toFixed(3) : RADIUS_BOUNDS.step
      radiusInput.value = imperial ? newRadius.toFixed(3) : newRadius
      this.radiusDisplay = parseFloat(radiusInput.value)

      // Min altitude: metres ↔ feet
      const curMinAlt = parseFloat(minAltInput.value) || MIN_ALT_BOUNDS.min
      const newMinAlt = imperial ? mToFt(curMinAlt) : ftToM(curMinAlt)
      minAltInput.min   = imperial ? (MIN_ALT_BOUNDS.min  * FT_PER_M).toFixed(0) : MIN_ALT_BOUNDS.min
      minAltInput.max   = imperial ? (MIN_ALT_BOUNDS.max  * FT_PER_M).toFixed(0) : MIN_ALT_BOUNDS.max
      minAltInput.step  = imperial ? (MIN_ALT_BOUNDS.step * FT_PER_M).toFixed(0) : MIN_ALT_BOUNDS.step
      minAltInput.value = Math.round(newMinAlt)

      // Max altitude: metres ↔ feet
      const curMaxAlt = parseFloat(maxAltInput.value) || MAX_ALT_BOUNDS.min
      const newMaxAlt = imperial ? mToFt(curMaxAlt) : ftToM(curMaxAlt)
      maxAltInput.min   = imperial ? (MAX_ALT_BOUNDS.min  * FT_PER_M).toFixed(0) : MAX_ALT_BOUNDS.min
      maxAltInput.max   = imperial ? (MAX_ALT_BOUNDS.max  * FT_PER_M).toFixed(0) : MAX_ALT_BOUNDS.max
      maxAltInput.step  = imperial ? (MAX_ALT_BOUNDS.step * FT_PER_M).toFixed(0) : MAX_ALT_BOUNDS.step
      maxAltInput.value = Math.round(newMaxAlt)

      this.fieldsAreImperial = imperial

      // Keep the Leaflet circle in sync (always sized in metres).
      if (this._circle) {
        const displayRadius = parseFloat(radiusInput.value) || RADIUS_BOUNDS.min
        const radiusKm = imperial ? miToKm(displayRadius) : displayRadius
        this._circle.setRadius(radiusKm * 1000)
        this._map?.fitBounds(this._circle.getBounds(), { padding: [20, 20] })
      }
    },

    // ── Custom template autocomplete ──────────────────────────────────────────

    // Read valid field/symbol names from the reference table that is already
    // rendered in the DOM.  Single source of truth – no duplicated list.
    collectTemplateTagNames() {
      const tagNames = []
      const codes = document.querySelectorAll(
        '#custom_template_panel table tbody tr td:first-child code'
      )
      codes.forEach(code => {
        const text = code.textContent.trim()
        if (text.startsWith('{symbol:')) {
          const name = text.replace('{symbol:', '').replace('}', '').split(':')[0]
          if (name) tagNames.push('symbol:' + name)
        } else if (text === '{heading_arrow}') {
          tagNames.push('heading_arrow')
        } else if (text === '{heading_direction}') {
          tagNames.push('heading_direction')
        } else if (text && !text.startsWith('{')) {
          tagNames.push(text)
        }
      })
      this.autocomplete.tagNames = tagNames
    },

    onTemplateInput(e) {
      const textarea = e.target
      const val      = textarea.value
      const cursor   = textarea.selectionStart

      // Find the last unclosed `{` before the cursor.
      const lastOpen = val.lastIndexOf('{', cursor - 1)
      if (lastOpen === -1) { this.hideAutocomplete(); return }

      // If a `}` appears between the `{` and the cursor the tag is already closed.
      const closeAfterOpen = val.indexOf('}', lastOpen)
      if (closeAfterOpen !== -1 && closeAfterOpen < cursor) { this.hideAutocomplete(); return }

      const partial  = val.substring(lastOpen + 1, cursor).toLowerCase()
      const matches  = this.autocomplete.tagNames
        .filter(n => n.toLowerCase().startsWith(partial))
        .sort()

      if (matches.length === 0) { this.hideAutocomplete(); return }

      const position = this.getCaretCoordinates(textarea)
      this.autocomplete.items         = matches
      this.autocomplete.selectedIndex = -1
      this.autocomplete.position      = { left: position.x, top: textarea.offsetHeight }
      this.autocomplete.visible       = true
    },

    onTemplateKeydown(e) {
      if (!this.autocomplete.visible || this.autocomplete.items.length === 0) return

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        this.autocomplete.selectedIndex = Math.min(
          this.autocomplete.selectedIndex + 1,
          this.autocomplete.items.length - 1
        )
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        this.autocomplete.selectedIndex = Math.max(this.autocomplete.selectedIndex - 1, 0)
      } else if ((e.key === 'Enter' || e.key === 'Tab') && this.autocomplete.selectedIndex >= 0) {
        e.preventDefault()
        this.insertTag(this.autocomplete.items[this.autocomplete.selectedIndex])
      } else if (e.key === 'Escape') {
        this.hideAutocomplete()
      }
    },

    insertTag(tagName) {
      const textarea = document.getElementById('details_custom_template')
      const start    = textarea.selectionStart
      const val      = textarea.value
      const bracePos = val.lastIndexOf('{', start - 1)
      if (bracePos === -1) { this.hideAutocomplete(); return }

      const insertion = tagName + '}'
      const newVal    = val.substring(0, bracePos + 1) + insertion + val.substring(start)
      textarea.value  = newVal
      const newCursor = bracePos + 1 + insertion.length
      textarea.setSelectionRange(newCursor, newCursor)
      textarea.focus()

      this.customTemplate = newVal   // keep v-model in sync
      this.hideAutocomplete()
    },

    hideAutocomplete() {
      this.autocomplete.visible       = false
      this.autocomplete.items         = []
      this.autocomplete.selectedIndex = -1
    },

    // Approximate caret (x, y) inside the textarea using a mirror div.
    getCaretCoordinates(textarea) {
      const style = window.getComputedStyle(textarea)
      const mirror = document.createElement('div')
      Object.assign(mirror.style, {
        position:   'absolute',
        visibility: 'hidden',
        whiteSpace: 'pre-wrap',
        font:       style.font,
        fontSize:   style.fontSize,
        fontFamily: style.fontFamily,
        lineHeight: style.lineHeight,
        padding:    style.padding,
        border:     style.border,
        boxSizing:  'border-box',
        width:      textarea.clientWidth + 'px',
      })
      mirror.textContent = textarea.value.substring(0, textarea.selectionStart)
      const caret = document.createElement('span')
      caret.textContent = '|'
      mirror.appendChild(caret)
      document.body.appendChild(mirror)
      const textareaRect = textarea.getBoundingClientRect()
      const caretRect    = caret.getBoundingClientRect()
      const x = caretRect.left - textareaRect.left
      document.body.removeChild(mirror)
      return { x }
    },

    // ── Form submission ────────────────────────────────────────────────────────

    onFormSubmit(e) {
      // Convert displayed imperial values back to stored metric units before
      // the browser packages the form fields into the POST body.
      if (this.fieldsAreImperial) {
        const radiusInput = document.getElementById('flight_radius')
        const minAltInput = document.getElementById('flight_min_altitude')
        const maxAltInput = document.getElementById('flight_max_altitude')

        radiusInput.value = miToKm(parseFloat(radiusInput.value) || RADIUS_BOUNDS.min)
        minAltInput.value = ftToM(parseFloat(minAltInput.value)  || MIN_ALT_BOUNDS.min)
        maxAltInput.value = ftToM(parseFloat(maxAltInput.value)  || MAX_ALT_BOUNDS.min)

        this.fieldsAreImperial = false
      }

      // Require a WeatherAPI key when weather is enabled.
      const weatherMode = document.querySelector('input[name="weather_mode"]:checked')?.value ?? '0'
      const weatherKey  = document.getElementById('weatherapi_key').value.trim()
      if (weatherMode !== '0' && !weatherKey) {
        e.preventDefault()
        this.weatherKeyError = true
        document.getElementById('group-weather-data')
          .scrollIntoView({ behavior: 'smooth', block: 'center' })
        // Restore display-unit values so the form still shows miles/feet.
        this.applyUnitToFields()
        return
      }

      this.weatherKeyError = false
      this.isSaving        = true
    },
  },

}).use(router).mount('#settings-app')
