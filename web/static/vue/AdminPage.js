/**
 * Admin page - logging, password, cache, backup, help, version.
 */

import { defineComponent } from "./vendor.js";

export default defineComponent({
  name: "AdminPage",
  props: {
    store: { type: Object, required: true },
  },
  data() {
    return {
      newPassword: "",
      confirmPassword: "",
    };
  },
  template: `
    <div>
    <h2 class="fs-4 fw-semibold mb-3"><i class="bi bi-shield-lock me-2"></i>Admin</h2>

    <!-- ====== Logging ====== -->
    <div id="group-logging" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-terminal me-2"></i>Logging</p>
      <div class="mb-3">
        <h5>Log Level</h5>
        <select class="form-select form-select-sm" name="log_level" style="max-width:200px"
                v-model="store.config.log_level">
          <option value="DEBUG">Debug (verbose)</option>
          <option value="INFO">Info (default)</option>
          <option value="WARNING">Warning</option>
          <option value="ERROR">Error</option>
          <option value="CRITICAL">Critical</option>
        </select>
        <div class="form-text text-muted small">
          Controls how much detail is captured for the
          <a :href="store.ui.urls.logs">log viewer</a>. Change requires a restart.
        </div>
      </div>
      <div class="form-check">
        <input type="checkbox" class="form-check-input" id="provider_usage_logging"
               name="provider_usage_logging" :value="true"
               v-model="store.config.provider_usage_logging" />
        <label class="form-check-label small" for="provider_usage_logging">
          Record provider API usage
        </label>
        <div class="form-text text-muted small">
          Counts how often each lookup provider is used and how often they come back empty.
          View the totals on the
          <a :href="store.ui.urls.statusApi">API Usage</a> page. Turning this off stops new
          tallies; recorded history is kept until cleared there.
        </div>
      </div>
    </div>

    <!-- ====== Cache ====== -->
    <div id="group-clear-cache" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-database me-2"></i>Cache</p>
      <div class="row g-3 mb-2">
        <div class="col-12 col-md-6">
          <label class="form-label small mb-1" for="cache_aircraft_days">
            Aircraft cache duration (days)
          </label>
          <input type="number" class="form-control form-control-sm" id="cache_aircraft_days"
                 name="cache_aircraft_days" min="1" max="30" step="1"
                 v-model.number="store.config.cache_aircraft_days" style="width:8rem" />
          <div class="form-text text-muted small">
            How long aircraft details are reused from cache (1-30 days) before
            providers are asked again.
          </div>
        </div>
        <div class="col-12 col-md-6">
          <label class="form-label small mb-1" for="cache_route_hours">
            Route cache duration (hours)
          </label>
          <input type="number" class="form-control form-control-sm" id="cache_route_hours"
                 name="cache_route_hours" min="1" max="48" step="1"
                 v-model.number="store.config.cache_route_hours" style="width:8rem" />
          <div class="form-text text-muted small">
            How long callsign routing is reused from cache (1-48 hours) before
            providers are asked again. Short is safer - flight numbers move between
            routes - but costs more lookups.
          </div>
        </div>
      </div>
      <div class="d-flex align-items-center justify-content-between flex-wrap gap-2 border-top pt-3">
        <div>
          <div class="text-muted small">Clears cached lookup data and the TLE cache.</div>
          <div class="fw-semibold">Clearing cache will restart FlightTracker.</div>
        </div>
        <a :href="store.ui.urls.cacheClear" class="btn btn-outline-danger btn-sm">
          <i class="bi bi-trash3 me-1"></i>Clear Cache
        </a>
      </div>
    </div>

    <!-- ====== Backup ====== -->
    <div id="group-backup" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-file-earmark-arrow-down me-2"></i>Backup</p>
      <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
        <div>
          <div class="text-muted small">
            Download a full copy of your settings (including API keys) or restore from a previous export.
          </div>
          <div class="fw-semibold">Restoring will overwrite all settings and restart.</div>
        </div>
        <div class="d-flex gap-2 flex-wrap">
          <a :href="store.ui.urls.backupExport" class="btn btn-outline-primary btn-sm">
            <i class="bi bi-download me-1"></i>Export
          </a>
          <a :href="store.ui.urls.backupRestore" class="btn btn-outline-warning btn-sm">
            <i class="bi bi-upload me-1"></i>Restore
          </a>
        </div>
      </div>
    </div>

    <!-- ====== Change Password ====== -->
    <div id="group-password" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-key me-2"></i>Change Password</p>
      <div class="row g-3">
        <div class="col-sm-6">
          <label class="form-label small">New password</label>
          <input type="password" class="form-control form-control-sm"
                 name="new_password" id="new_password" autocomplete="new-password"
                 v-model="newPassword" placeholder="Leave blank to keep current" />
        </div>
        <div class="col-sm-6">
          <label class="form-label small">Confirm new password</label>
          <input type="password" class="form-control form-control-sm"
                 name="confirm_password" id="confirm_password" autocomplete="new-password"
                 v-model="confirmPassword" placeholder="Repeat new password" />
        </div>
      </div>
    </div>

    <!-- ====== Version ====== -->
    <div id="group-version" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-info-circle me-2"></i>Version</p>
      <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
        <div>
          <div class="text-muted small">Current version</div>
          <div class="fs-5 fw-semibold">{{ store.ui.currentVersion }}</div>
          <a :href="store.ui.urls.update" class="btn btn-outline-warning btn-sm mt-2">
            <i class="bi bi-arrow-repeat me-1"></i>Check for Updates
          </a>
        </div>
      </div>
    </div>

    <!-- ====== Help & Support ====== -->
    <div id="group-help" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-question-circle me-2"></i>Help &amp; Support</p>
      <div class="text-muted small mb-2">
        <p>
          Found a bug or need a hand? Open an issue on
          <a href="https://github.com/ColinWaddell/FlightTracker/issues" target="_blank">GitHub</a>.
        </p>
        <p>
          If you need to post your config data use the button below, it removes your password and
          API keys making it safe to post online.
        </p>
      </div>
      <a :href="store.ui.urls.debugConfig" class="btn btn-sm btn-outline-secondary">
        <i class="bi bi-download me-1"></i>Download debug config
      </a>
    </div>
    </div>
  `,
});