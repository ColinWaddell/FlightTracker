/**
 * Sky Monitoring page - location, airport display, airline info,
 * plane details, and satellite tracking.
 */

import { defineComponent } from "./vendor.js";
import SimpleMap from "./SimpleMap.js";
import AdvancedMap from "./AdvancedMap.js";
import TemplateEditor from "./TemplateEditor.js";

export default defineComponent({
  name: "SkyMonitoringPage",
  components: { SimpleMap, AdvancedMap, TemplateEditor },
  props: {
    store: { type: Object, required: true },
  },
  template: `
    <div>
    <h2 class="fs-4 fw-semibold mb-3"><i class="bi bi-rocket-takeoff-pin me-2"></i>Sky Monitoring</h2>

    <!-- ====== Location ====== -->
    <div id="group-sky-monitoring" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-geo-alt me-2"></i>Location</p>

      <h5>Tracking Mode</h5>
      <div class="mb-3">
        <div class="btn-group w-100 mb-1" role="group" aria-label="Tracking mode">
          <input type="radio" class="btn-check" name="flight_location_mode" id="location_mode_simple"
                 value="simple" autocomplete="off"
                 v-model="store.config.flight_location_mode" />
          <label class="btn btn-outline-primary btn-sm" for="location_mode_simple">
            <i class="bi bi-circle me-1"></i>Simple
          </label>

          <input type="radio" class="btn-check" name="flight_location_mode" id="location_mode_advanced"
                 value="advanced" autocomplete="off"
                 v-model="store.config.flight_location_mode" />
          <label class="btn btn-outline-primary btn-sm" for="location_mode_advanced">
            <i class="bi bi-bounding-box me-1"></i>Advanced
          </label>
        </div>

        <div v-if="!store.isAdvancedLocation" class="form-text text-muted small">
          Set a centre point and search radius. The bounding box for flight data queries and your
          observer location (used for weather, satellite passes, and distance sorting) are both
          derived from this point.
        </div>
        <div v-else class="form-text text-muted small">
          Draw a search box for flight data queries and place your observer location separately.
          The observer location is used for weather, satellite passes, and distance sorting.
          <ul class="mb-0 mt-1 ps-3">
            <li><strong>Unlock:</strong> click the unlock icon to adjust</li>
            <li><strong>Single click:</strong> move the observer marker to the clicked location</li>
            <li><strong>Drag:</strong> drag the marker or the box corners to adjust their positions</li>
            <li><strong>Double click:</strong> set the observer marker and centre a 10&nbsp;km search box around the clicked location</li>
          </ul>
        </div>
        <div class="form-text text-muted small mt-2">
          I know this isn't great on mobile right now, but it'll get fixed soon.
        </div>
      </div>

      <!-- Simple tracking -->
      <div v-show="!store.isAdvancedLocation">
        <simple-map :store="store" />

        <div class="mb-3">
          <label class="form-label">
            Search Radius: {{ store.displayRadius.toFixed(1) }} {{ store.radiusUnitLabel }}
          </label>
          <input type="range" class="form-range pt-3 px-2" id="flight_radius"
                 :min="store.radiusBoundsDisplay.min"
                 :max="store.radiusBoundsDisplay.max"
                 :step="store.radiusBoundsDisplay.step"
                 v-model.number="store.displayRadius" />
          <!-- Hidden field submits the stored (km) value -->
          <input type="hidden" name="flight_radius" :value="store.config.flight_radius" />
        </div>
      </div>

      <!-- Advanced tracking -->
      <div v-show="store.isAdvancedLocation">
        <advanced-map :store="store" />
      </div>

      <hr class="my-3" />
      <h5>Altitude Filter</h5>
      <div class="row g-3">
        <div class="col">
          <label class="form-label small">Min Altitude ({{ store.altitudeUnitLabel }})</label>
          <input type="number" :step="store.minAltBoundsDisplay.step"
                 :min="store.minAltBoundsDisplay.min"
                 :max="store.minAltBoundsDisplay.max"
                 class="form-control form-control-sm" id="flight_min_altitude"
                 v-model.number="store.displayMinAlt" />
          <input type="hidden" name="flight_min_altitude" :value="store.config.flight_min_altitude" />
        </div>
        <div class="col">
          <label class="form-label small">Max Altitude ({{ store.altitudeUnitLabel }})</label>
          <input type="number" :step="store.maxAltBoundsDisplay.step"
                 :min="store.maxAltBoundsDisplay.min"
                 :max="store.maxAltBoundsDisplay.max"
                 class="form-control form-control-sm" id="flight_max_altitude"
                 v-model.number="store.displayMaxAlt" />
          <input type="hidden" name="flight_max_altitude" :value="store.config.flight_max_altitude" />
        </div>
      </div>
      <p class="form-text small text-muted mt-1 mb-0">
        <i class="bi bi-info-circle me-1"></i>Setting a non-zero minimum altitude (say,
        <code>{{ store.altitudeHelpExample }}</code>) prevents the device always listing
        aircraft on the tarmac.
      </p>
    </div>

    <!-- ====== Airport Display ====== -->
    <div id="group-airport-display" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-building me-2"></i>Airport Display</p>

      <h5>Display Style</h5>
      <div class="mb-3">
        <div class="form-check">
          <input type="radio" class="form-check-input" name="airport_display_style" id="airport_short"
                 :value="0" v-model.number="store.config.airport_display_style" />
          <label class="form-check-label" for="airport_short">Short airport code</label>
        </div>
        <div class="form-check">
          <input type="radio" class="form-check-input" name="airport_display_style" id="airport_name"
                 :value="1" v-model.number="store.config.airport_display_style" />
          <label class="form-check-label" for="airport_name">Airport name</label>
        </div>
        <div class="form-check">
          <input type="radio" class="form-check-input" name="airport_display_style" id="airport_name_abbrev"
                 :value="2" v-model.number="store.config.airport_display_style" />
          <label class="form-check-label" for="airport_name_abbrev">Airport name, abbreviated</label>
        </div>
        <div class="form-check">
          <input type="radio" class="form-check-input" name="airport_display_style" id="airport_muni"
                 :value="3" v-model.number="store.config.airport_display_style" />
          <label class="form-check-label" for="airport_muni">Airport municipality</label>
        </div>
        <div class="form-check">
          <input type="radio" class="form-check-input" name="airport_display_style" id="airport_muni_country"
                 :value="4" v-model.number="store.config.airport_display_style" />
          <label class="form-check-label" for="airport_muni_country">Airport municipality and country</label>
        </div>
      </div>


      <div v-show="store.config.airport_display_style === 0" class="mb-3">
        <hr />
        
        <h5>Home Airport</h5>
        <input type="text" maxlength="6" class="form-control form-control-sm"
               name="home_airport_code" id="home_airport_code"
               :value="store.config.home_airport_code"
               @input="store.config.home_airport_code = $event.target.value.toUpperCase()"
               placeholder="e.g. GLA"
               style="text-transform:uppercase;max-width:120px" />
        <div class="form-text text-muted small">{{ store.homeAirportHint }}</div>
        <div class="form-text text-muted small mt-1">
          When a flight's origin or destination matches this code, that airport will appear
          <strong>bold</strong> on the display. Leave blank to disable.
        </div>
      </div>

      <hr />

      <h5>Unknown Airport Placeholder</h5>
      <div class="mb-2">
        <input type="text" maxlength="3" class="form-control form-control-sm"
               name="journey_blank_filler"
               v-model="store.config.journey_blank_filler"
               style="max-width:120px" />
        <div class="form-text text-muted small mt-1">Code to be displayed when no airport information is available.</div>
      </div>

      <hr />

      <h5>Extended Airport Lookup</h5>
      <div class="mb-2 form-check">
        <input type="checkbox" class="form-check-input" name="airport_lookup_full" id="airport_lookup_full"
               v-model="store.config.airport_lookup_full" />
        <label class="form-check-label" for="airport_lookup_full">Include local airport codes</label>
        <div class="form-text text-muted small">
          Also look up FAA/local airport codes (e.g. 0I8, 98KY) so small municipal
          airports and hospital heliports show a name instead of "Unknown". Uses a
          larger bundled table; off by default.
        </div>
      </div>
    </div>

    <!-- ====== Airline Info ====== -->
    <div id="group-airline-info" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-ticket-perforated me-2"></i>Airline Info</p>

      <h5>Airline Logo</h5>
      <div class="mb-2 form-check">
        <input type="checkbox" class="form-check-input" name="show_airline_icon" id="show_airline_icon"
               v-model="store.config.show_airline_icon" />
        <label class="form-check-label" for="show_airline_icon">Show airline logo</label>
        <div class="form-text text-muted small">
          Displays a 16x16 airline icon in the top-left corner, derived from the flight's callsign prefix.
        </div>
      </div>

      <hr />

      <h5>Flight ID</h5>
      <div class="mb-3">
        <div class="form-check">
          <input type="radio" class="form-check-input" name="info_bar_mode" id="info_bar_mode_callsign"
                 value="callsign" v-model="store.config.info_bar_mode" />
          <label class="form-check-label" for="info_bar_mode_callsign">Show callsign</label>
        </div>
        <div class="form-check">
          <input type="radio" class="form-check-input" name="info_bar_mode" id="info_bar_mode_airline"
                 value="airline" v-model="store.config.info_bar_mode" />
          <label class="form-check-label" for="info_bar_mode_airline">Show airline name</label>
        </div>
        <div class="form-check">
          <input type="radio" class="form-check-input" name="info_bar_mode" id="info_bar_mode_callsign_airline"
                 value="callsign_airline" v-model="store.config.info_bar_mode" />
          <label class="form-check-label" for="info_bar_mode_callsign_airline">Show callsign and airline name</label>
        </div>
        <div class="form-text text-muted small">
          Show the flight's callsign (e.g. BAW123) or the operating airline's name (e.g. British Airways) in the info bar.
        </div>
      </div>

      <hr />

      <h5>Callsign Format</h5>
      <div class="mb-3">
        <div class="form-check">
          <input type="radio" class="form-check-input" name="callsign_format" id="callsign_format_icao"
                 value="icao" v-model="store.config.callsign_format" />
          <label class="form-check-label" for="callsign_format_icao">ICAO callsign (e.g. BAW123)</label>
        </div>
        <div class="form-check">
          <input type="radio" class="form-check-input" name="callsign_format" id="callsign_format_iata"
                 value="iata" v-model="store.config.callsign_format" />
          <label class="form-check-label" for="callsign_format_iata">IATA flight number (e.g. BA123)</label>
        </div>
        <div class="form-text text-muted small">
          Choose whether to display the ICAO callsign or IATA flight number. Falls back to ICAO when the IATA number is unavailable.
        </div>
      </div>
    </div>

    <!-- ====== Plane Info Row ====== -->
    <div id="group-plane-info" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-info-circle me-2"></i>Plane Info Row</p>
      <h5>Display Mode</h5>
      <div class="mb-2">
        <div class="form-check">
          <input type="radio" class="form-check-input" name="details" id="details_model"
                 :value="0" v-model.number="store.config.details" />
          <label class="form-check-label" for="details_model">Aircraft make &amp; model</label>
        </div>
        <div class="form-check">
          <input type="radio" class="form-check-input" name="details" id="details_tlm"
                 :value="1" v-model.number="store.config.details" />
          <label class="form-check-label" for="details_tlm">Telemetry (altitude / speed / heading)</label>
        </div>
        <div class="form-check">
          <input type="radio" class="form-check-input" name="details" id="details_custom"
                 :value="2" v-model.number="store.config.details" />
          <label class="form-check-label" for="details_custom">Custom template</label>
        </div>
      </div>
      <div class="form-text text-muted small">
        Shown in the scrolling bar at the bottom of the display while a flight is overhead.
      </div>

      <template-editor v-if="store.config.details === 2" :store="store" />
    </div>

    <!-- ====== Satellite Tracking ====== -->
    <div id="group-satellite" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-rocket-takeoff me-2"></i>Satellite Tracking</p>

      <p class="form-text text-muted small mb-2">
        This feature allows you to track satellites (including the ISS) and display their passes over
        your location. TLE data is fetched automatically from CelesTrak.
      </p>

      <div class="form-check mb-3">
        <input type="checkbox" class="form-check-input" id="satellite_tracking_enabled"
               name="satellite_tracking_enabled" :value="true"
               v-model="store.config.satellite_tracking_enabled" />
        <label class="form-check-label small" for="satellite_tracking_enabled">Enable satellite tracking</label>
      </div>

      <div v-show="store.config.satellite_tracking_enabled">
        <h5>Satellites to Track</h5>
        <div class="mb-3">
          <label class="form-label small" for="satellite_norad_ids">NORAD IDs</label>
          <textarea class="form-control form-control-sm font-monospace" id="satellite_norad_ids"
                    name="satellite_norad_ids" rows="4" placeholder="25544"
                    v-model="store.noradIdsText"></textarea>
          <div class="form-text text-muted small">
            One NORAD catalog ID per line. ISS&nbsp;=&nbsp;25544. Look up IDs on
            <a href="https://celestrak.org/SATCAT/search.php" target="_blank" rel="noopener noreferrer">CelesTrak</a>.
            TLEs are fetched automatically and cached for 24 hours.
          </div>
        </div>

        <hr class="my-3" />
        <h5>Pass Filter</h5>
        <div class="row g-2 mb-2">
          <div class="col-auto">
            <label class="form-label small" for="satellite_min_elevation">Minimum elevation (°)</label>
            <input type="number" class="form-control form-control-sm" id="satellite_min_elevation"
                   name="satellite_min_elevation" v-model.number="store.config.satellite_min_elevation"
                   min="0" max="90" style="width:5rem" />
            <div class="form-text text-muted small">Passes that don't reach this elevation above the horizon are ignored.</div>
          </div>
          <div class="col-auto">
            <label class="form-label small" for="satellite_max_count">Max simultaneous satellites</label>
            <input type="number" class="form-control form-control-sm" id="satellite_max_count"
                   name="satellite_max_count" v-model.number="store.config.satellite_max_count"
                   min="1" max="10" style="width:5rem" />
          </div>
        </div>

        <hr class="my-3" />
        <h5>Display Timeout</h5>
        <div class="mb-2 form-check">
          <input type="checkbox" class="form-check-input" id="satellite_timeout_enabled"
                 name="satellite_timeout_enabled" :value="true"
                 v-model="store.config.satellite_timeout_enabled" />
          <label class="form-check-label small" for="satellite_timeout_enabled">Limit display time per pass</label>
        </div>

        <div v-show="store.config.satellite_timeout_enabled" class="mb-2">
          <label class="form-label small" for="satellite_timeout_seconds">Timeout (seconds)</label>
          <input type="number" class="form-control form-control-sm" id="satellite_timeout_seconds"
                 name="satellite_timeout_seconds" v-model.number="store.config.satellite_timeout_seconds"
                 min="5" max="3600" style="width:6rem" />
          <div class="form-text text-muted small">
            The satellite scene will yield to flight tracking after this many seconds from a pass's start (AOS),
            even if the satellite is still overhead. A new pass beginning within the window will keep the scene active.
          </div>
        </div>
      </div>
    </div>
    </div>
  `,
});