/**
 * Root Vue application for the settings page.
 *
 * Holds the reactive store, manages routing (page visibility), handles
 * sidebar navigation (scroll-to-section), and form submission.
 */

import { defineComponent, ref, onMounted, nextTick } from "./vendor.js";
import { createStore } from "./store.js";
import SettingsSidebar from "./SettingsSidebar.js";
import SkyMonitoringPage from "./SkyMonitoringPage.js";
import DataSourcePage from "./DataSourcePage.js";
import DefaultScreenPage from "./DefaultScreenPage.js";
import HardwarePage from "./HardwarePage.js";
import AdminPage from "./AdminPage.js";

const PAGES = [
  { name: "sky-monitoring", component: SkyMonitoringPage },
  { name: "data-source", component: DataSourcePage },
  { name: "default-screen", component: DefaultScreenPage },
  { name: "hardware", component: HardwarePage },
  { name: "admin", component: AdminPage },
];

export default defineComponent({
  name: "SettingsApp",
  components: { SettingsSidebar, SkyMonitoringPage, DataSourcePage, DefaultScreenPage, HardwarePage, AdminPage },
  setup() {
    const config = window.FT_CONFIG || {};
    const pageData = window.FT_PAGE_DATA || {};

    const store = createStore(config, pageData);

    const currentPage = ref("sky-monitoring");

    function showPage(pageName) {
      currentPage.value = pageName;
    }

    function scrollToSection(section) {
      nextTick(() => {
        const target = document.getElementById(section);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }

    function navigate({ route, section }) {
      const pageName = route.replace(/^\//, "");
      const currentPath = currentPage.value;

      if (currentPath === pageName) {
        scrollToSection(section);
      } else {
        showPage(pageName);
        setTimeout(() => scrollToSection(section), 80);
      }
    }

    // -- Form submission --------------------------------------------------
    function onSubmit(e) {
      // Validate weather key when weather is enabled
      const weatherMode = store.config.weather_mode;
      const weatherKey = (store.config.weatherapi_key || "").trim();

      if (weatherMode !== 0 && !weatherKey) {
        e.preventDefault();
        store.ui.weatherKeyError = true;
        const target = document.getElementById("group-weather-data");
        if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }

      store.ui.weatherKeyError = false;
      store.ui.saving = true;
      // Let the browser submit the form normally
    }

    // -- Restore hash from URL on load --
    onMounted(() => {
      const hash = window.location.hash.replace(/^#\/?/, "");
      if (hash && PAGES.some((p) => p.name === hash)) {
        showPage(hash);
      }
    });

    return {
      store,
      currentPage,
      pages: PAGES,
      navigate,
      onSubmit,
      scrollToSection,
    };
  },
  template: `
    <div class="container-fluid py-4" style="max-width:1100px">
      <div class="row">
        <!-- Sidebar -->
        <div class="col-md-3 mb-4">
          <settings-sidebar @navigate="navigate" />
        </div>

        <!-- Main content -->
        <div class="col-md-9">
          <form method="post" action="/settings" id="settings-form" novalidate @submit="onSubmit">
            <input type="hidden" name="csrf_token" :value="store.ui.csrfToken" />

            <!-- Template errors alert -->
            <div v-if="store.ui.templateErrors.length" class="alert alert-danger mb-3">
              <strong><i class="bi bi-exclamation-triangle me-1"></i>Template errors:</strong>
              Please fix the following issues in the
              <a href="javascript:void(0)"
                 @click="scrollToSection('group-plane-info')"
                 class="alert-link fw-bold">Plane Details</a>
              section:
              <ul class="mb-0 mt-1">
                <li v-for="err in store.ui.templateErrors" :key="err">{{ err }}</li>
              </ul>
            </div>

            <!-- Import failed alert -->
            <div v-if="store.ui.importFailed" class="alert alert-warning alert-dismissible fade show mb-3" role="alert">
              <strong><i class="bi bi-exclamation-triangle me-1"></i>Import failed:</strong>
              The last config import failed and your previous settings have been restored.
              <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>

            <!-- Server error alert -->
            <div v-if="store.ui.serverError" class="alert alert-danger mb-3">
              <strong>Error saving settings:</strong> {{ store.ui.serverError }}
            </div>

            <!-- Page content (only the active page is rendered) -->
            <component
              v-for="page in pages"
              :is="page.component"
              v-show="currentPage === page.name"
              :key="page.name"
              :store="store"
            />

            <!-- Save button -->
            <div class="d-grid mb-3">
              <button type="submit" id="save-btn" class="btn btn-primary btn-lg" :disabled="store.ui.saving">
                <span v-if="store.ui.saving" class="spinner-border spinner-border-sm me-2" role="status"></span>
                {{ store.ui.saving ? 'Saving…' : 'Save & Restart' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  `,
});