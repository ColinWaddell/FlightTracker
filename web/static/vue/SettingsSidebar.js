/**
 * Sidebar navigation - Vue Router links with scroll-to-section.
 */

import { defineComponent, ref } from "./vendor.js";
import { SIDEBAR_GROUPS } from "./store.js";

export default defineComponent({
  name: "SettingsSidebar",
  emits: ["navigate"],
  setup(props, { emit }) {
    const groups = SIDEBAR_GROUPS;
    const mobileCollapse = ref(false);

    return { groups, mobileCollapse };
  },
  template: `
    <div class="sidebar" id="settings-sidebar">
      <button class="btn btn-outline-secondary btn-sm w-100 mb-2 d-md-none"
              type="button"
              @click="mobileCollapse = !mobileCollapse"
              :aria-expanded="mobileCollapse">
        <i class="bi bi-list me-1"></i>Configuration Menu
      </button>

      <div class="d-md-block" :class="{ 'd-none': !mobileCollapse }">
        <div v-for="group in groups" :key="group.title" class="menu-section">
          <div class="group-header">
            <i :class="['bi', group.icon, 'me-2']"></i>{{ group.title }}
          </div>
          <nav class="nav flex-column">
            <a v-for="item in group.items" :key="item.section"
               class="nav-link"
               :href="'#' + group.route"
               :data-section="item.section"
               @click.prevent="onNavigate(group.route, item.section)">
              <i :class="['bi', item.icon, 'me-2']"></i>{{ item.label }}
            </a>
          </nav>
        </div>
      </div>
    </div>
  `,
  methods: {
    onNavigate(route, section) {
      this.$emit("navigate", { route, section });
    },
  },
});