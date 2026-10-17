/*
 * Self-hosted Ko-fi support widget (paired with web/static/kofi/kofi.css
 * and injected by web/templates/kofi.html).
 *
 * Re-implements Ko-fi's "floating-chat" overlay widget without loading any
 * third-party JavaScript.  The Ko-fi page - which has to be served by
 * ko-fi.com - is only fetched, inside an iframe, the first time the popup
 * opens, so the page itself stays completely self-contained.
 */
(function () {
  "use strict";

  var KOFI_PAGE = "flighttracker";

  /* Height limits mirror the original widget (desktop: 400-690). */
  var POPUP_MAX_HEIGHT = 690;
  var POPUP_MIN_HEIGHT = 320;

  var button = document.getElementById("kofi-donate-button");
  var popup = document.getElementById("kofi-popup");
  var closer = document.getElementById("kofi-popup-closer");
  var iframeContainer = document.getElementById("kofi-popup-iframe-container");

  if (!button || !popup || !closer || !iframeContainer) {
    return;
  }

  var isOpen = false;
  var popupIframe = null;

  function popupHeight() {
    /* Same idea as the original widget: fill most of the space above the
     * button, leaving headroom at the top of the viewport, then clamp. */
    var height = Math.min(POPUP_MAX_HEIGHT, window.innerHeight - 141);
    return Math.max(POPUP_MIN_HEIGHT, Math.min(height, window.innerHeight - 90));
  }

  function ensureIframe() {
    if (popupIframe) {
      return;
    }
    popupIframe = document.createElement("iframe");
    popupIframe.src =
      "https://ko-fi.com/" + KOFI_PAGE + "/?hidefeed=true&widget=true&embed=true";
    popupIframe.title = "Support FlightTracker on Ko-fi";
    iframeContainer.appendChild(popupIframe);
  }

  function render() {
    popup.classList.toggle("open", isOpen);
    popup.style.height = isOpen ? popupHeight() + "px" : "0px";
    popup.inert = !isOpen;
    popup.setAttribute("aria-hidden", isOpen ? "false" : "true");
    button.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }

  function setOpen(state) {
    if (state) {
      ensureIframe();
    }
    isOpen = state;
    render();
  }

  button.addEventListener("click", function () {
    setOpen(!isOpen);
  });
  closer.addEventListener("click", function () {
    setOpen(false);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && isOpen) {
      setOpen(false);
    }
  });
  window.addEventListener("resize", function () {
    if (isOpen) {
      popup.style.height = popupHeight() + "px";
    }
  });
})();