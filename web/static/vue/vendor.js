/**
 * Tiny ES module wrapper around the global Vue object.
 *
 * The page loads Vue from a CDN <script> tag (so it ends up on
 * `window.Vue`).  This module re-exports it as ES module imports so
 * the rest of the codebase can use clean
 * `import { createApp } from "./vendor.js"` syntax.
 */

export const Vue = window.Vue;

export const {
  createApp,
  h,
  defineComponent,
  ref,
  reactive,
  computed,
  watch,
  onMounted,
  onUnmounted,
  nextTick,
} = Vue;