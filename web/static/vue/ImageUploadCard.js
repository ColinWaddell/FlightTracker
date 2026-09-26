/*
 * ImageUploadCard - "Image Upload API" card for the Data Source page.
 *
 * Displays the current API key (masked, with a Show Key toggle) and
 * handles generation/revocation via the JSON key endpoints in
 * web/image_api.py.  Uses fetch() rather than the main settings form
 * (which knows nothing about this feature), so every button must be
 * type="button" to avoid submitting the surrounding settings form.
 */

import { defineComponent, computed, ref, onMounted } from "./vendor.js";

export default defineComponent({
  name: "ImageUploadCard",
  props: {
    store: { type: Object, required: true },
  },
  setup(props) {
    // null = still checking, true/false = configured or not
    const keyStatus = ref(null);
    const keyValue = ref(null); // plaintext; masked in the input
    const showKey = ref(false);
    const busy = ref(false);
    const error = ref("");

    // The panel's render loop (setup/frames.py PERIOD = 80ms) is scaled
    // by the display speed setting; animation is quantised to it.
    const animationPeriodMs = computed(() => {
      const factor = { default: 1.0, slower: 2.0, faster: 0.75 }[
        props.store.config.display_speed
      ] || 1.0;
      return Math.round(80 * factor);
    });
    const animationFps = computed(() =>
      (1000 / animationPeriodMs.value).toFixed(1)
    );

    onMounted(loadStatus);

    async function loadStatus() {
      try {
        const resp = await fetch("/api/image-key");
        if (!resp.ok) return; // leave the "checking" state alone on auth errors
        const data = await resp.json();
        keyStatus.value = !!data.configured;
        keyValue.value = data.key || null;
      } catch {
        // network hiccup - leave the status pending
      }
    }

    async function generateKey() {
      busy.value = true;
      error.value = "";
      try {
        const resp = await fetch("/api/image-key", {
          method: "POST",
          headers: { "X-CSRF-Token": props.store.ui.csrfToken },
        });
        const data = await resp.json();
        if (!resp.ok) {
          error.value = data.error || "Key generation failed";
        } else {
          keyValue.value = data.key;
          keyStatus.value = true;
          showKey.value = true; // reveal what was just generated
        }
      } catch {
        error.value = "Key generation failed";
      } finally {
        busy.value = false;
      }
    }

    async function revokeKey() {
      busy.value = true;
      error.value = "";
      try {
        const resp = await fetch("/api/image-key", {
          method: "DELETE",
          headers: { "X-CSRF-Token": props.store.ui.csrfToken },
        });
        const data = await resp.json();
        if (!resp.ok) {
          error.value = data.error || "Key revocation failed";
        } else {
          keyStatus.value = false;
          keyValue.value = null;
          showKey.value = false;
        }
      } catch {
        error.value = "Key revocation failed";
      } finally {
        busy.value = false;
      }
    }

    return { keyStatus, keyValue, showKey, busy, error, animationPeriodMs, animationFps, generateKey, revokeKey };
  },
  template: `
    <div id="group-image-upload" class="card mb-3 p-3">
      <p class="section-heading"><i class="bi bi-image me-2"></i>Image Upload API</p>

      <h5>API Key</h5>
      <div class="mb-3">
        <div v-if="keyStatus === null" class="text-muted small">Checking key status&hellip;</div>
        <template v-else>
          <div v-if="keyStatus" class="input-group input-group-sm mb-2" style="max-width:560px">
            <input :type="showKey ? 'text' : 'password'"
                   class="form-control font-monospace"
                   readonly :value="keyValue || ''"
                   id="image-api-key" />
            <button v-if="keyValue" type="button" class="btn btn-outline-secondary"
                    @click="showKey = !showKey">{{ showKey ? "Hide Key" : "Show Key" }}</button>
            <button type="button" class="btn btn-outline-danger" :disabled="busy"
                    @click="revokeKey">Revoke</button>
          </div>
          <div class="mb-2">
            <button type="button" class="btn btn-sm btn-primary" :disabled="busy" @click="generateKey">
              {{ keyStatus ? "Regenerate Key" : "Generate Key" }}
            </button>
          </div>
          <div v-if="keyStatus && !keyValue" class="form-text text-muted small mb-2">
            A key is configured but predates viewable keys - regenerate it to see it here.
          </div>
          <div v-else-if="!keyStatus" class="form-text text-muted small mb-2">
            No API key configured - the upload endpoint is disabled until you generate one.
          </div>
          <div v-if="error" class="form-text small" style="color:#dc3545">{{ error }}</div>
        </template>
      </div>

      <hr class="my-3" />
      <h5>Usage</h5>
      <div class="form-text text-muted small">
        <p class="mb-1">Push images to the display with an HTTP POST. Each frame is the raw RGB
        panel image (64x32, 6144 bytes) base64-encoded. The image stays up for
        frames &times; frame_delay &times; loops, then the normal display returns:</p>
        <pre class="mb-2" style="font-size:0.75rem"><code>curl -X POST http://&lt;host&gt;:{{ store.config.web_port }}/api/image \\
  -H "X-API-Key: ***;your key&gt;" -H "Content-Type: application/json" \\
  -d '{"data": ["&lt;base64 frame&gt;"], "frame_delay": 60000}'</code></pre>
        <pre class="mb-1" style="font-size:0.75rem"><code>{
  "data": ["&lt;base64 frame&gt;"],
  "loops": 3,
  "frame_delay": 150
}</code></pre>
        <table class="table table-sm table-borderless mb-0" style="font-size:0.75rem">
          <tbody>
            <tr><td class="text-nowrap pe-2"><code>data</code></td><td>One base64 frame per entry - raw RGB, 6144 bytes each (1-60 frames).</td></tr>
            <tr><td class="text-nowrap pe-2"><code>loops</code></td><td>Optional play-throughs (default 1).</td></tr>
            <tr><td class="text-nowrap pe-2"><code>frame_delay</code></td><td>Optional ms each frame is held (default 500, 10-60000), rounded to whole display frames.</td></tr>
          </tbody>
        </table>
        <p class="mt-2 mb-0">The panel animates at {{ animationFps }} fps ({{ animationPeriodMs }} ms per
        frame), so <code>frame_delay</code> values are rounded to whole frames - the API response
        reports the effective timing.</p>
        <p class="mt-2 mb-0"><i class="bi bi-github me-1"></i> See
        <a href="https://github.com/ColinWaddell/FlightTracker-ImageUploader" target="_blank">FlightTracker-ImageUploader</a>,
        a ready-made command-line client that pushes images to the screen.</p>
      </div>
    </div>
  `,
});