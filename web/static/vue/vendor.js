/**
 * Tiny ES module wrapper around the global Vue / VueRouter objects.
 *
 * The page loads Vue and VueRouter from CDNs as <script> tags (so they
 * end up on `window.Vue` / `window.VueRouter`).  This module re-exports
 * them as ES module imports so the rest of the codebase can use clean
 * `import { createApp } from "./vendor.js"` syntax.
 */

export const Vue = window.Vue;
export const VueRouter = window.VueRouter;

export const { createApp, h, defineComponent, ref, reactive, computed, watch, onMounted, onUnmounted, nextTick } = Vue;
export const { createRouter, createWebHashHistory } = VueRouter;