---
layout: base.njk
title: "FlightTracker OS - Prebuilt Raspberry Pi Image"
description: "FlightTracker OS is a pre-built Raspberry Pi image for the Pi 3, 4 and 5. Flash it with Raspberry Pi Imager, set your Wi-Fi, and configure everything from your browser - no command line required."
permalink: "/os/"
og_type: "website"
og_title: "FlightTracker OS - No command line required"
og_image: "/images/installer/web-installer.png"
structured_data: |
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "FlightTracker OS",
    "operatingSystem": "Raspberry Pi OS",
    "applicationCategory": "MakerApplication",
    "description": "A pre-built Raspberry Pi image that turns a Pi 3, 4 or 5 and an RGB LED matrix into a flight tracker. Flash it with Raspberry Pi Imager and configure it from your browser - no command line required.",
    "url": "https://flight-tracker.dev/os/",
    "downloadUrl": "https://github.com/ColinWaddell/FlightTracker-Image/releases",
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "GBP"
    },
    "author": {
      "@type": "Person",
      "name": "Colin Waddell",
      "url": "https://colinwaddell.com"
    },
    "license": "https://www.gnu.org/licenses/gpl-3.0.html",
    "image": "https://flight-tracker.dev/images/installer/web-installer.png"
  }
---

<div class="status-bar">
  <div class="status-item"><a href="#what-is-it" class="text-black">What is it?</a></div>
  <div class="status-item"><a href="#flash" class="text-black">Set up the card</a></div>
  <div class="status-item"><a href="#step-by-step" class="text-black">Step by step</a></div>
  <div class="status-item"><a href="#first-boot" class="text-black">Run on device</a></div>
  <div class="status-item"><a href="#web-installer" class="text-black">Web installer</a></div>
  <div class="status-item"><a href="#downloads" class="text-black">Downloads</a></div>
</div>

<section id="what-is-it" class="border-bottom">
  <div class="container">
    <h1 class="section-title">What is FlightTracker OS?</h1>

    <div class="row g-4 align-items-center">
      <div class="col-lg-7">
        <div class="narrative">
          <p>FlightTracker OS is a pre-built Raspberry Pi image that has everything installed and configured for you - no command line required.</p>
          <p>It bundles the FlightTracker software, the RGB matrix drivers, and a web-based installer into a single image. You flash it to an SD card, power up, and finish setup from your browser.</p>
          <p>It supports the Raspberry Pi 3, 4, and 5, in both 32-bit and 64-bit flavours. If you're using a Pi Zero, Pi Zero W, or Pi Zero 2, use the <a href="/install/#quick-install">quick-install script</a> over SSH instead.</p>
          <p>Flash it to an SD card with <a href="https://www.raspberrypi.com/software/" target="_blank">Raspberry Pi Imager</a>, set your Wi-Fi details, flash, and boot.
          You can then log into the web installer and finish setup from your browser.</p>
        </div>
      </div>
      <div class="col-lg-5">
        <div class="card">
          <div class="card-body p-2">
            <img src="/images/installer/web-installer.png" alt="FlightTracker OS web installer" loading="lazy" class="w-100 d-block">
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<section id="flash" class="border-bottom">
  <div class="container">
    <h2 class="section-title">Flashing the image</h2>

    <div class="narrative">
      <p>If you have Raspberry Pi Imager 2.x installed, you can write the FlightTracker OS image straight to an SD card using <a href="https://www.raspberrypi.com/software/" target="_blank">RPi Imager</a>.</p>

      <div class="rpi-imager-btn-wrap">
        <a class="btn btn-rpi mb-3" href="rpi-imager://open?repo=https%3A%2F%2Fraw.githubusercontent.com%2FColinWaddell%2FFlightTracker-Image%2Frefs%2Fheads%2Fmain%2Fos_list.json">
          <img src="/images/Raspberry_Pi_Logo.svg" width="40"> Click To Install With RPi Imager
        </a>
      </div>

      <p class="small text-muted mb-2">
        <a href="https://www.raspberrypi.com/software/" target="_blank">RPi Imager</a> will ask you to confirm the custom repository before loading it.
      </p>

      <p class="mb-2">
        If the button does not work, open <a href="https://www.raspberrypi.com/software/" target="_blank">RPi Imager</a> and add this URL manually
        under <strong>App Options → Content Repository → Custom URL</strong>:
      </p>
    </div>

    <div class="code-card">
      <div class="code-card-header">
        <span>FlightTracker OS Images</span>
        <button class="code-card-copy" onclick="copyCode(this, 'https://raw.githubusercontent.com/ColinWaddell/FlightTracker-Image/refs/heads/main/os_list.json')">Copy</button>
      </div>
      <div class="code-card-body">
        <pre><code>https://raw.githubusercontent.com/ColinWaddell/FlightTracker-Image/refs/heads/main/os_list.json</code></pre>
      </div>
    </div>

    <div class="narrative">
      <h4>How it works</h4>
      <ul>
        <li>Follow the details above to open up the image in RPi Imager</li>
        <li>Select your device type and whether you want the 32-bit or 64-bit version installed
          <ul>
            <li>32-bit is best for Pi 3 (32-bit compatibility)</li>
            <li>64-bit should be good for everything else</li>
          </ul>
        </li>
        <li>Set your Wi-Fi details</li>
        <li>Choose a device name (e.g. <code><strong>flighttracker</strong></code>)</li>
        <li>Let RPi Imager prepare your SD card</li>
        <li>Once it's finished remove the card from your computer and put it in your Raspberry Pi</li>
        <li>Power everything up</li>
        <li>The Pi connects to your Wi-Fi automatically using the credentials you (hopefully) set earlier</li>
        <li>Visit <code>http://<strong>flighttracker</strong>.local:8584/</code> in your browser (tweak the url based on the hostname you gave this device).</li>
        <li>The web installer guides you through the rest</li>
        <li>When it's done the Pi reboots and the FlightTracker app starts up on the matrix</li>
      </ul>
    </div>
  </div>
</section>

<section id="step-by-step" class="border-bottom">
  <div class="container">
    <h2 class="section-title">Step by step</h2>

    <div class="narrative">
      <p>First, download and install <a href="https://www.raspberrypi.com/software/">Raspberry Pi Imager</a> on your computer.</p>

      <div class="alert alert-info border-info border-2" role="alert">
        <p class="mb-0">Use a decent quality microSD card with at least <strong>8GB</strong> of space. Cheap cards can cause random crashes and slow installs, and they have a higher chance of randomly dying.</p>
      </div>

      <p>Stick a microSD card into your computer and open the Imager. The steps are:</p>

      <ol>
        <li><strong>Choose your device</strong> - pick the Raspberry Pi model you're using (3B, 4B, 5, etc.).</li>
      </ol>
    </div>

    <div class="narrative">
        <div class="card mb-3">
            <div class="card-header">Select your device</div>
            <div class="card-body p-2">
                <img src="/images/installer/001_select_your_device.png" alt="Raspberry Pi Imager device selection screen" loading="lazy" class="w-100 d-block">
            </div>
            </div>

            <div class="narrative">
            <ol start="2">
                <li><strong>Choose your OS</strong> - after loading the FlightTracker repository (using the button or URL above), pick <em>FlightTracker</em> from the OS list, then choose the version for your Pi. Go with 64-bit unless you have a Pi 3, in which case pick 32-bit.</li>
            </ol>
            </div>

            <div class="card mb-3">
            <div class="card-header">Choose your OS</div>
            <div class="card-body p-2">
                <img src="/images/installer/flight-tracker-os-install-option.png" alt="Raspberry Pi Imager OS selection screen showing the FlightTracker OS 64-bit and 32-bit options" loading="lazy" class="w-100 d-block">
            </div>
        </div>
    </div>

    <div class="narrative">
      <ol start="3">
        <li><strong>Choose your storage</strong> - select your microSD card. Double-check you've picked the right one, because everything on it is about to be wiped.</li>
        <li><strong>Edit the settings</strong> - before you write, the Imager will offer to apply OS customisation settings. This is where you set up:
          <ul>
            <li>A <strong>hostname</strong> for your Pi (something like <code>flighttracker</code> makes it easy to find on your network).</li>
            <li>Your <strong>Wi-Fi</strong> details, so the Pi can join your network on first boot.</li>
          </ul>
        </li>
      </ol>
    </div>

    <div class="narrative">
        <div class="card mb-3">
            <div class="card-header">Configure Wi-Fi</div>
            <div class="card-body p-2">
                <img src="/images/installer/004_choose_wifi.png" alt="Raspberry Pi Imager OS customisation screen showing Wi-Fi configuration" loading="lazy" class="w-100 d-block">
            </div>
        </div>
    </div>

    <div class="narrative">
      <ol start="4">
        <li><strong>Write</strong> - hit the button and wait. The Imager writes the image, verifies it, and applies your settings in one go.</li>
      </ol>
      <p>Once that's done, eject the card, slot it into your Pi, and power it on - then head to <a href="#first-boot">first boot</a> below.</p>
    </div>
  </div>
</section>

<section id="first-boot" class="border-bottom">
  <div class="container">
    <h2 class="section-title">Run on the device</h2>

    <div class="narrative">
      <p>Once the card is written, eject it, slot it into your Pi, and power it on. Give it a minute or two to boot and join your network using the Wi-Fi credentials you set in the Imager.</p>
      <p>On first boot the screen stays dark while the system prepares itself - the FlightTracker app doesn't start until the web installer has finished. Instead, the device brings up a small web server you can reach from your browser at <code>http://flighttracker.local:8584</code> (using the hostname you set in the Imager) or <code>http://&lt;your-pi-ip&gt;:8584</code>.</p>
    </div>

    <div class="narrative">
      <p>If the <code>.local</code> hostname doesn't resolve on your network, you can find the Pi's IP address from your router's admin page and use that instead.</p>
    </div>
  </div>
</section>

<section id="web-installer" class="border-bottom">
  <div class="container">
    <h2 class="section-title">Load the web installer</h2>

    <div class="narrative">
      <p>When you open the web interface you're greeted by the built-in web installer. It guides you through the remaining setup steps from your browser.</p>
    </div>

    <div class="narrative">
      <div class="card mb-3">
        <div class="card-header">Web installer in FlightTracker OS</div>
        <div class="card-body p-2">
          <img src="/images/installer/web-installer.png" alt="Install the Flight Tracker software using the web installer in FlightTracker OS" loading="lazy" class="w-100 d-block">
        </div>
      </div>
    </div>

    <div class="narrative">
      <p>After the installation process completes the device will reboot and the FlightTracker app starts for real: the matrix comes to life and shows the QR code splash screen so you can scan it with your phone and jump straight back into the configuration UI. The same web UI is always available at <code>http://flighttracker.local:8584</code>.</p>
    </div>

    <div class="narrative">
      <div class="card">
        <div class="card-header">After the installer reboots - scan to configure</div>
        <div class="card-body p-2 bg-black">
          <img src="/images/captures/qr_code.png" alt="FlightTracker QR code splash screen shown after the installer has finished" loading="lazy" class="w-100 d-block">
        </div>
      </div>
    </div>
  </div>
</section>

<section id="downloads">
  <div class="container">
    <h2 class="section-title">Downloads</h2>

    <div class="narrative">
      <p>Pre-built images are available to download directly from the
      <a href="https://github.com/ColinWaddell/FlightTracker-Image/releases">releases page</a> on GitHub, if you'd rather flash the image file yourself.</p>
      <p>Prefer to build things up yourself? The <a href="/install/">install guide</a> covers the quick installer script, manual installation, and upgrading from v1.</p>
    </div>
  </div>
</section>