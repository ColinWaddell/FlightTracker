/**
 * Custom plane-info template editor with brace-balance indicator and
 * {tag} autocomplete.
 *
 * Reads from / writes to: store.config.details_custom_template
 * Uses TEMPLATE_FIELDS and TEMPLATE_SYMBOLS from the store for the
 * reference table and autocomplete source.
 */

import { defineComponent, ref, computed, onMounted, onUnmounted, nextTick } from "./vendor.js";
import { TEMPLATE_FIELDS, TEMPLATE_SYMBOLS } from "./store.js";

// Build a flat list of autocomplete tag names from the reference data.
const AUTOCOMPLETE_TAGS = [
  ...TEMPLATE_FIELDS.filter((f) => !f.units).map((f) => f.name),
  ...TEMPLATE_SYMBOLS.map((s) =>
    s.tag.startsWith("{symbol:")
      ? "symbol:" + s.tag.replace("{symbol:", "").replace("}", "").split(":")[0]
      : s.tag.replace(/[{}]/g, ""),
  ),
];

export default defineComponent({
  name: "TemplateEditor",
  props: {
    store: { type: Object, required: true },
  },
  setup(props) {
    const textarea = ref(null);
    const dropdown = ref(null);
    const dropdownVisible = ref(false);
    const dropdownItems = ref([]);
    const selectedIndex = ref(-1);
    const symbolImages = props.store.ui.symbolImages || {};

    const value = computed({
      get: () => props.store.config.details_custom_template || "",
      set: (v) => {
        props.store.config.details_custom_template = v;
      },
    });

    const braceBalanced = computed(() => props.store.braceBalanced.value);
    const braceMessage = computed(() => props.store.braceMessage.value);
    const templateErrors = computed(() => props.store.ui.templateErrors);

    // -- Autocomplete logic ------------------------------------------------

    function getCaretCoordinates() {
      const el = textarea.value;
      if (!el) return { x: 0, y: 0 };
      const style = window.getComputedStyle(el);
      const div = document.createElement("div");
      div.style.position = "absolute";
      div.style.visibility = "hidden";
      div.style.whiteSpace = "pre-wrap";
      div.style.font = style.font;
      div.style.fontSize = style.fontSize;
      div.style.fontFamily = style.fontFamily;
      div.style.lineHeight = style.lineHeight;
      div.style.padding = style.padding;
      div.style.border = style.border;
      div.style.boxSizing = "border-box";
      div.style.width = el.clientWidth + "px";
      div.textContent = el.value.substring(0, el.selectionStart);
      const span = document.createElement("span");
      span.textContent = "|";
      div.appendChild(span);
      document.body.appendChild(div);
      const rect = el.getBoundingClientRect();
      const spanRect = span.getBoundingClientRect();
      const x = spanRect.left - rect.left;
      const y = spanRect.top - rect.top + spanRect.height;
      document.body.removeChild(div);
      return { x, y };
    }

    function showDropdown(items) {
      dropdownItems.value = items;
      selectedIndex.value = -1;
      dropdownVisible.value = items.length > 0;
      if (dropdownVisible.value) {
        nextTick(() => {
          const coords = getCaretCoordinates();
          if (dropdown.value) {
            dropdown.value.style.left = coords.x + "px";
            dropdown.value.style.top = textarea.value.offsetHeight + "px";
          }
        });
      }
    }

    function hideDropdown() {
      dropdownVisible.value = false;
      dropdownItems.value = [];
      selectedIndex.value = -1;
    }

    function insertTag(tagName) {
      const el = textarea.value;
      if (!el) return;
      const start = el.selectionStart;
      const end = el.selectionEnd;
      const val = el.value;
      const bracePos = val.lastIndexOf("{", start - 1);
      if (bracePos === -1) {
        hideDropdown();
        return;
      }
      const insertion = tagName + "}";
      const newVal = val.substring(0, bracePos + 1) + insertion + val.substring(end);
      props.store.config.details_custom_template = newVal;
      const newCursor = bracePos + 1 + insertion.length;
      nextTick(() => {
        el.setSelectionRange(newCursor, newCursor);
        el.focus();
      });
      hideDropdown();
    }

    function onInput() {
      const el = textarea.value;
      if (!el) return;
      const val = el.value;
      const cursor = el.selectionStart;

      const lastOpen = val.lastIndexOf("{", cursor - 1);
      if (lastOpen === -1) {
        hideDropdown();
        return;
      }

      const closeAfterOpen = val.indexOf("}", lastOpen);
      if (closeAfterOpen !== -1 && closeAfterOpen < cursor) {
        hideDropdown();
        return;
      }

      const partial = val.substring(lastOpen + 1, cursor).toLowerCase();
      const matches = AUTOCOMPLETE_TAGS.filter((name) =>
        name.toLowerCase().startsWith(partial),
      ).sort();

      if (matches.length === 0) {
        hideDropdown();
        return;
      }
      showDropdown(matches);
    }

    function onKeydown(e) {
      if (!dropdownVisible.value || dropdownItems.value.length === 0) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        selectedIndex.value = Math.min(
          selectedIndex.value + 1,
          dropdownItems.value.length - 1,
        );
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        selectedIndex.value = Math.max(selectedIndex.value - 1, 0);
      } else if (e.key === "Enter" || e.key === "Tab") {
        if (selectedIndex.value >= 0) {
          e.preventDefault();
          insertTag(dropdownItems.value[selectedIndex.value]);
        }
      } else if (e.key === "Escape") {
        hideDropdown();
      }
    }

    function onDocumentClick(e) {
      if (
        textarea.value &&
        dropdown.value &&
        e.target !== textarea.value &&
        !dropdown.value.contains(e.target)
      ) {
        hideDropdown();
      }
    }

    onMounted(() => {
      document.addEventListener("click", onDocumentClick);
    });

    onUnmounted(() => {
      document.removeEventListener("click", onDocumentClick);
    });

    return {
      textarea,
      dropdown,
      dropdownVisible,
      dropdownItems,
      selectedIndex,
      value,
      braceBalanced,
      braceMessage,
      templateErrors,
      fields: TEMPLATE_FIELDS,
      symbols: TEMPLATE_SYMBOLS,
      symbolImages,
      onInput,
      onKeydown,
      insertTag,
      hideDropdown,
    };
  },
  template: `
    <div class="mt-3 position-relative">
      <hr class="my-2" />
      <label class="form-label small fw-bold" for="details_custom_template">
        Template string
        <span v-if="templateErrors.length" class="badge bg-danger ms-1">Template Error</span>
      </label>
      <textarea
        ref="textarea"
        class="form-control form-control-sm font-monospace"
        name="details_custom_template"
        id="details_custom_template"
        rows="3"
        placeholder="{plane} | {symbol:altitude} {altitude}"
        autocomplete="off"
        v-model="value"
        @input="onInput"
        @keydown="onKeydown"
      ></textarea>

      <div v-if="!braceBalanced" class="form-text small" style="color:#dc3545">
        {{ braceMessage }}
      </div>

      <div class="form-text text-muted small">
        Define what appears in the scrolling bar using tags and literal text. See the reference below.
      </div>

      <!-- Autocomplete dropdown -->
      <div
        v-if="dropdownVisible"
        ref="dropdown"
        class="template-autocomplete"
      >
        <div
          v-for="(item, i) in dropdownItems"
          :key="item"
          class="template-autocomplete-item"
          :class="{ 'template-autocomplete-active': i === selectedIndex }"
          @mouseenter="selectedIndex = i"
          @mousedown.prevent="insertTag(item)"
        >{{ item }}</div>
      </div>

      <!-- Reference panel -->
      <div class="mt-3 p-3 bg-light rounded border">
        <p class="fw-bold small mb-2"><i class="bi bi-book me-1"></i>Template Reference</p>

        <p class="small fw-bold mb-1">Syntax</p>
        <ul class="small text-muted mb-2" style="line-height:1.5">
          <li><code>{field}</code> - show a flight field (uses default unit for telemetry)</li>
          <li><code>{field:unit}</code> - show a field with a specific unit (e.g. <code>{altitude:ft}</code>)</li>
          <li><code>{field:#RRGGBB}</code> - show a field in a custom colour (e.g. <code>{altitude:#FF8800}</code>)</li>
          <li><code>{field:unit:#RRGGBB}</code> - both unit and colour</li>
          <li><code>{symbol:name}</code> - insert an icon glyph</li>
          <li>Any text outside <code>{}</code> is shown as-is (e.g. <code> | </code>, <code> -> </code>)</li>
        </ul>

        <p class="small fw-bold mb-1">Available fields</p>
        <table class="table table-sm table-bordered mb-2" style="font-size:0.8rem">
          <thead class="table-light">
            <tr><th>Field</th><th>Shows</th><th>Units</th></tr>
          </thead>
          <tbody>
            <tr><td colspan="3" class="fw-bold bg-light">Text fields</td></tr>
            <template v-for="f in fields" :key="f.name">
              <tr v-if="!f.units">
                <td><code>{{ f.name }}</code></td>
                <td>{{ f.label }}</td>
                <td>-</td>
              </tr>
            </template>
            <tr><td colspan="3" class="fw-bold bg-light">Telemetry fields</td></tr>
            <template v-for="f in fields" :key="f.name">
              <tr v-if="f.units">
                <td><code>{{ f.name }}</code></td>
                <td>{{ f.label }}</td>
                <td><code>{{ f.units }}</code></td>
              </tr>
            </template>
          </tbody>
        </table>

        <p class="small fw-bold mb-1">Symbols</p>
        <table class="table table-sm table-bordered mb-2" style="font-size:0.8rem">
          <thead class="table-light">
            <tr><th>Tag</th><th>Icon</th><th>Meaning</th></tr>
          </thead>
          <tbody>
            <tr v-for="s in symbols" :key="s.tag">
              <td><code>{{ s.tag }}</code></td>
              <td>
                <img v-if="symbolImages[s.tag]"
                     :src="symbolImages[s.tag]" alt="" style="height:20px" />
                <span v-else class="text-muted small">icon</span>
              </td>
              <td>{{ s.label }}</td>
            </tr>
          </tbody>
        </table>

        <p class="small fw-bold mb-1">Colours</p>
        <p class="small text-muted mb-2">
          Add <code>#RRGGBB</code> to any tag to override its colour.
          Omitting it uses the current theme's default colours.
        </p>

        <p class="small fw-bold mb-1">Examples</p>
        <ul class="small text-muted mb-0" style="line-height:1.6">
          <li><code>{plane}</code> - just the aircraft model</li>
          <li><code>{symbol:altitude} {altitude} {symbol:speed} {ground_speed} {symbol:heading} {heading}{symbol:degree}</code> - full telemetry with icons</li>
          <li><code>{callsign} | {origin} -> {destination} | {altitude:ft:#FF8800}</code> - callsign, route, orange altitude</li>
          <li><code>{plane} ({registration}) {symbol:altitude} {altitude:m} {symbol:speed} {speed:knots}</code> - model, reg, metric altitude, knots</li>
          <li><code>{heading}{symbol:degree} {heading_arrow}</code> - heading value with directional arrow</li>
          <li><code>{heading}{symbol:degree} {heading_direction} {heading_arrow}</code> - heading value, cardinal direction text, and directional arrow</li>
        </ul>
      </div>
    </div>
  `,
});