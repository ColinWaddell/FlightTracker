---
layout: base.njk
title: "The Build"
description: "How FlightTracker was built - the case, the electronics, and the software."
permalink: "/build/"
---

<section>
  <div class="container">
    <h2 class="section-title">What to buy</h2>
    <p class="section-sub">You do not need anything exotic. Here's the lot.</p>

    <div class="narrative">
      <p>The core of FlightTracker is a Raspberry Pi, an RGB LED matrix, and the Adafruit bonnet that wires them together. Beyond that, it's a power supply and a microSD card - and optionally a case, a fancy connector, and a switch that looks like a tiny antenna.</p>

      <p>The links below are to the UK suppliers I used. The same parts are available from Adafruit, Amazon, and Raspberry Pi stockists worldwide.</p>
    </div>

    <div class="info-panel" style="margin-bottom: 24px;">
      <div class="info-panel-header">The essentials</div>
      <div class="info-panel-body">
        {% include "hardware-grid.njk" %}
        <p style="color: var(--muted); margin-top: 16px; margin-bottom: 0;">These are the parts you actually need to run FlightTracker. The case and the fancy connector are optional - nice, but not required.</p>
      </div>
    </div>

    <!-- TODO: Write the "where to buy outside the UK" note - point readers to Adafruit (US), Pimoroni (UK/EU), The Pi Hut, and local Raspberry Pi stockists. Mention that the matrix panels are widely available under a few brand names. -->

    <!-- TODO: Write the "what you don't need" callout - no soldering iron strictly required (the bonnet comes pre-assembled), no 3D printer required, no special tools beyond a microSD card writer. Note the optional solder bridge on the bonnet for cleaner PWM. -->
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">The nice-to-haves</h2>
    <div class="narrative">
      <p>None of these are required. They are the parts that made <em>my</em> build feel finished - the Lemo connector because it's gorgeous, the switch because it looks like a tiny antenna, the case because a bare matrix on the fridge is a bit sad.</p>
      <p>Skip them all if you just want it working. Come back to them later if you catch the bug.</p>
    </div>

    <!-- TODO: Write a short paragraph per optional extra explaining why you might want it and where to get it. Pull from the build page and the _junk blog post. -->
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">Ready to build?</h2>
    <div class="narrative">
      <p>Once you've got the parts, head to the <a href="/install/">install guide</a> to get FlightTracker running on your Pi.</p>
    </div>
    <p style="margin-top: 32px;">
      <a href="/install/" class="btn btn-yellow">How to install →</a>
    </p>
  </div>
</section>