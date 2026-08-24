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
    <h2 class="fs-4 fw-semibold mb-3"><i class="bi bi-shield-lock me-2"></i>Admin</h2>

    <!-- ====== Logging ====== -->
    <div id="group-logging" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-terminal me-2"></i>Logging</p>
      <div class="mb-3">
        <label class="form-label small">Log level</label>
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

    <!-- ====== Clear Cache ====== -->
    <div id="group-clear-cache" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-trash3 me-2"></i>Clear Cache</p>
      <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
        <div>
          <div class="text-muted small">Remove cached JSON files used by route and TLE lookups.</div>
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
  `,
});