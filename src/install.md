---
layout: base.njk
title: "Get Started"
description: "Install FlightTracker on your Raspberry Pi in one line."
permalink: "/install/"
---

<section>
  <div class="container">
    <h2 class="section-title">Get started</h2>
    <p class="section-sub">Set up your Raspberry Pi with Raspberry Pi OS Bookworm first, then run the command below.</p>

    <div class="narrative">
      <p>This page is the friendly version. If you want every manual step spelled out - the driver install, the virtual environment, the systemd service - the <a href="{{ site.repo }}#installation">README</a> has the full reference install.</p>
      <p>The script below does all of that for you.</p>
    </div>

    <div class="info-panel" style="margin-bottom: 24px;">
      <div class="info-panel-header">One-line install</div>
      <div class="info-panel-body">
        <div class="code-block">curl -fsSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/main/install.sh | bash</div>
        <p style="color: var(--muted); margin-top: 16px; margin-bottom: 0;">
          <!-- TODO: Host the install.sh script in the FlightTracker repo and confirm this URL. The script should: update apt, install the rgb-matrix driver, clone FlightTracker, create the venv, install requirements, install the matrix Python bindings, and set up the systemd service. -->
          This installs the RGB matrix driver, clones FlightTracker, sets up the Python environment, and configures the service to run on boot.
        </p>
      </div>
    </div>

    <div class="info-panel" style="margin-bottom: 24px;">
      <div class="info-panel-header">What the script does</div>
      <div class="info-panel-body">
        <ul class="config-list">
          <li>Updates your system packages</li>
          <li>Installs the Adafruit RGB matrix driver to <code style="font-family: var(--mono); background: var(--panel-2); padding: 2px 6px;">/home/pi/rpi-rgb-led-matrix</code></li>
          <li>Clones FlightTracker to <code style="font-family: var(--mono); background: var(--panel-2); padding: 2px 6px;">/home/pi/FlightTracker</code></li>
          <li>Creates a Python virtual environment and installs the dependencies</li>
          <li>Installs the matrix Python bindings into the virtual environment</li>
          <li>Sets up a systemd service so FlightTracker starts on boot</li>
        </ul>
        <p style="color: var(--muted); margin: 0;">You can read the script before you run it: <a href="{{ site.repo }}/blob/main/install.sh">view install.sh on GitHub</a>.</p>
      </div>
    </div>

    <div class="info-panel" style="margin-bottom: 24px;">
      <div class="info-panel-header">After install - first boot</div>
      <div class="info-panel-body">
        <div class="narrative">
          <p>On first boot, FlightTracker shows a QR code on the matrix. Scan it with your phone and finish setup in the web UI.</p>
          <p>From the web UI you can set your location, pick a theme, adjust brightness, and configure your data source. That feels much nicer than typing IP addresses into a terminal while standing in front of the fridge.</p>
        </div>
      </div>
    </div>

    <div class="info-panel">
      <div class="info-panel-header">Prefer the manual route?</div>
      <div class="info-panel-body">
        <p style="color: var(--muted); margin: 0;">If you'd rather run each step yourself - or you're installing on a non-standard setup - the full manual install is in the <a href="{{ site.repo }}#installation">README on GitHub</a>. It covers the driver install, the virtual environment, the config file, and the systemd service in detail.</p>
      </div>
    </div>

    <!-- TODO: Write the troubleshooting stub - link to GitHub Issues, mention common pitfalls (Bookworm vs Buster, username not pi, sound card conflict, permissions/setcap). -->
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">What you'll need</h2>
    <p class="section-sub">You do not need anything exotic.</p>

    <div class="info-panel">
      <div class="info-panel-header">A typical build uses</div>
      <div class="info-panel-body">
        {% include "hardware-grid.njk" %}
      </div>
    </div>

    <p style="margin-top: 24px;">
      <a href="/buy/" class="btn btn-yellow">See the full shopping list →</a>
    </p>
  </div>
</section>