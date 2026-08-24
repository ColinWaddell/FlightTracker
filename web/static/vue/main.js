/**
 * Entry point for the Vue settings page.
 *
 * Waits for the DOM to be ready, then mounts the root SettingsApp
 * component onto #settings-app.
 */

import { createApp } from "./vendor.js";
import SettingsApp from "./SettingsApp.js";

function mount() {
  const el = document.getElementById("settings-app");
  if (el) {
    createApp(SettingsApp).mount(el);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mount);
} else {
  mount();
}