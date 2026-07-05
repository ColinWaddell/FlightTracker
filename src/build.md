---
layout: base.njk
title: "The Build"
description: "How FlightTracker was built - the case, the electronics, and the software."
permalink: "/build/"
---

<section>
  <div class="container">
    <h2 class="section-title">What to buy</h2>

    <div class="narrative">
      <p>If you're considering building one of these then there's some must-have's and some optional extras.</p>
      <p>How you put it in a case I'll leave up to you.</p>
    </div>
    
    <h3>Minimum shopping list</h3>
    <div class="narrative">
      <p>There are cheaper alternatives to be found on the likes of Ali-Express for most things here, but if you want something to work first time I recommend going to a reputable retailer</p>
      
        <ul>
            <li>
                <a href="https://shop.pimoroni.com/products/rgb-led-matrix-panel?variant=42312764298">
                    RGB LED Matrix Panel - 32x64
                </a>
            </li>
            <li>
                <a href="https://shop.pimoroni.com/products/adafruit-rgb-matrix-bonnet-for-raspberry-pi?variant=2257849155594">
                    Adafruit RGB Matrix Bonnet for Raspberry Pi
                </a>
            </li>
            <li>
                <a href="https://www.amazon.co.uk/gp/product/B01DPXDB04/">
                    Power supply (5V 8A)
                </a>
            </li>
        </ul>

        <p>
            Plug everything together and you'll be ready to get the code running.

        </p>

        <div class="card">
          <div class="card-header">Connecting the bonnet to the Raspberry Pi</div>
          <div class="card-body p-2 bg-black">
            <img src="/images/bonnet_connection.jpg" alt="Connecting the RGB matrix bonnet to the Raspberry Pi" loading="lazy" class="w-100 d-block">
          </div>
          <div class="card-footer text-muted small">Image courtesy of <a href="https://shop.pimoroni.com/">Pimoroni</a></div>
        </div>
    </div>


    <h3>Optional Extras</h3>
    <div class="narrative">
        <p>
            When you put the device in a case it's nice to have a power switch on the side to toggle the device on and off. Additionally the code supports a blinking LED to indicate when the device is searching for overhead data.
        </p>
        <ul>
            <li>
                <a href="https://uk.farnell.com/nkk-switches/m2112tcw01/toggle-switch-1pole-red-led/dp/1187767">
                    Toggle switch with LED
                </a>
            </li>
        </ul>

        <h4>Simple Wiring</h4>
        <p>The simple version is to write power via the switch and hook the 5v directly to the LED. This is how it was originally wired in these pictures</p>

        <div class="row g-3">
          <div class="col-md-6">
            <div class="card h-100">
              <div class="card-header">Simple switch and LED wiring</div>
              <div class="card-body p-2 bg-black">
                <img src="/images/simple_wiring.jpg" alt="Simple wiring of a power switch and LED directly to the 5v supply" loading="lazy" class="w-100 d-block">
              </div>
            </div>
          </div>
          <div class="col-md-6">
            <div class="card h-100">
              <div class="card-header">Internals in the case</div>
              <div class="card-body p-2 bg-black">
                <img src="/images/internals-in-case.jpg" alt="The FlightTracker electronics fitted inside the case" loading="lazy" class="w-100 d-block">
              </div>
            </div>
          </div>
        </div>

        <h4>Blinky LED</h4> 
        <p>If you want that LED to blink when the device is searching for flights I recommend driving the LED indirectly via a transisitor to avoid asking too much of the GPIO output</p>

        <div class="card">
          <div class="card-header">Driving an LED indirectly via a transistor</div>
          <div class="card-body p-2 bg-black">
            <img src="/images/led_driver.png" alt="Circuit diagram showing how to drive an LED indirectly via a transistor" loading="lazy" class="w-100 d-block">
          </div>
        </div>

        <div class="narrative mb-4">
            <p><em>Looking for a way to contribute? I'd love some better illustrations of the various ways to wire up a FlightTracking box.</em>
        </p>
</div>
    </div>
  </div>
</section>