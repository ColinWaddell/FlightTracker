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
      <p>If you're considering building one of these, there are some must-haves and some optional extras. How you put it in a case I'll leave up to you.</p>
    </div>
    
    <h3>Minimum shopping list</h3>
    <div class="narrative">
      <p class="lead">A Raspberry Pi.<a href="https://www.raspberrypi.com/" target="_blank"><img src="/images/Raspberry_Pi_Logo.svg" alt="Raspberry Pi logo" width="20" class="mx-2"></img></a></p>
      <p>FlightTracker has been tested on:</p>
        <ul>
            <li>RPi 3B</li>
            <li>RPi 4B</li>
            <li>RPi Zero 2</li>
            <li>RPi Zero W</li>
            <li>RPi 5</li>
            <li><i>
                If your device isn't on this list and you're feeling brave, give it a shot and let me know
                if FlightTracker works.
            </i></li>
        </ul>

      <p>And the following bits for the display:</p>
      
        <ul>
            <li>
                <a href="https://shop.pimoroni.com/products/rgb-led-matrix-panel?variant=42312764298">
                    RGB LED Matrix Panel - 32x64 - 1:16 Scan Rate
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
      
        <p>There are cheaper alternatives to be found on the likes of AliExpress for most of the above, but if you want something to work first time I recommend going to a reputable retailer. In the UK I try and use <a href="https://shop.pimoroni.com/">Pimoroni</a> where possible.</p>

        <p>
            Plug everything together and you'll be ready to get the code running.
        </p>

        <div class="alert alert-warning" role="alert">
          Do not plug a USB power supply into your Pi at the same time as the RGB Matrix Bonnet's power supply. This can fry your Raspberry Pi. You only need the power connection that goes to the bonnet — it will supply power to the Pi as well.
        </div>

        <div class="card">
          <div class="card-header">Connecting the bonnet to the Raspberry Pi</div>
          <div class="card-body p-2 bg-black">
            <img src="/images/bonnet_connection.jpg" alt="Connecting the RGB matrix bonnet to the Raspberry Pi" loading="lazy" class="w-100 d-block">
          </div>
          <div class="card-footer text-muted small">Image courtesy of <a href="https://shop.pimoroni.com/">Pimoroni</a></div>
        </div>
    </div>

    <h3>Getting the best performance from the screen</h3>
    <div class="narrative">
        <p>
            If you're running the code on a Raspberry Pi 5 you can ignore this. For everyone else I recommend soldering a small bridge between the <code>4 (OE)</code> and <code>18</code> pin on the bonnet, <a href="https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/matrix-setup#configure-for-quality-slash-convenience-3201054" target="_blank">as per the guide.</a> It increases the quality by using the sound card to perform some
            of the data signalling, however this also means you can no longer use your sound card whilst the bonnet is plugged in.
        </p>

        <p>
            When installing the software you will be asked whether you soldered this connection.
        </p>

        <div class="card">
          <div class="card-header">Solder bridge location for best display quality</div>
          <div class="card-body p-2 bg-black">
            <img src="/images/led_matrices_gpios.jpg" alt="Solder bridge location for best quality" loading="lazy" class="w-100 d-block">
          </div>
          <div class="card-footer text-muted small">Image courtesy of <a href="https://adafruit.com/">Adafruit</a></div>
        </div>
        
    </div>

   <h2>Optional extras</h2>
    <div class="info-panel">
      <div class="info-panel-header">Optional extras</div>
      <div class="info-panel-body">
        <p>Everything after this point is <b>not needed</b> if you just want to build your own FlightTracker.</p>
        <p>A couple of people I know bought all the parts above, then got stuck because they wanted to make the "perfect" version of it.</p>
        <p>What follows is how I built mine. Don't treat it as a blueprint; it's just here for inspiration.</p>
      </div>
    </div>

    <h3>Toggle switch and power LED</h3>
    
    <div class="narrative">
        <p>
            When you put the device in a case it's nice to have a power switch on the side to toggle the device on and off. I use the following switch, which has a built-in LED to show when the device is powered.
        </p>
        <ul>
            <li>
                <a href="https://uk.farnell.com/nkk-switches/m2112tcw01/toggle-switch-1pole-red-led/dp/1187767">
                    Toggle switch with LED
                </a>
            </li>
        </ul>

        <div class="card mb-3">
          <div class="card-body p-2 bg-black">
            <img src="/images/blog/switch-light.jpg" alt="Toggle switch with LED light" loading="lazy" class="w-100 d-block">
          </div>
        </div>

        <h4>Simple wiring</h4>
        <p>The simple version is to wire power via the switch and hook the 5V directly to the LED. This is how it was originally wired in these pictures. You'll need to put a current limiting resistor between the LED and the 5V line. I think I went with around <code>330R</code>.</p>

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
        <p>If you want that LED to blink when the device is searching for flights I recommend driving the LED indirectly via a transistor to avoid asking too much of the GPIO output.</p>

        <div class="card mb-3">
        <div class="card-header">Wiring pin <code>25</code> of the Pi to the LED driver</div>
          <div class="card-body p-2 bg-black">
            <a href="/images/blog/blinky_wiring.jpeg">
              <img src="/images/blog/blinky_wiring.jpeg" alt="Blinky LED wiring" loading="lazy" class="w-100 d-block">
            </a>
          </div>
        </div>

        <p>I used the same <code>330R</code> resistor with an <a href="https://www.tindie.com/products/jeremycook/ez-fan2-tiny-raspberry-pi-fan-controller/">EZ Fan2 Tiny Raspberry Pi Fan Controller</a> by <a href="https://jeremyscook.com/">Jeremy Cook</a>. That gives you something like the following circuit to light up the LED.</p>

        <div class="card">
          <div class="card-header">Driving an LED indirectly via a transistor</div>
          <div class="card-body p-2 bg-black">
            <img src="/images/led_driver.png" alt="Circuit diagram showing how to drive an LED indirectly via a transistor" loading="lazy" class="w-100 d-block">
          </div>
        </div>

        <div class="narrative mb-4">
            <p><em>Looking for a way to contribute? I'd love some better instructions and illustrations of the various ways to wire up a FlightTracker box.</em></p>
        </div>
    
        <h2 class="section-title">Detailed circuits and illustrations</h2>
        <p>There aren't any. At the moment anything beyond the basic wiring is up to the person putting this together. Honestly, I find it difficult to know the amount of detail someone needs to wire something up if this is their first foray into a little bit of wiring. Do I need to explain how to use prototyping board?</p>

        <p>I could maybe have my arm twisted to release a dev board with everything pre-wired and you just
        plug in a Pi and a screen.</p>

        <p>If you've got strong feelings about this then raise an issue at GitHub and we can figure out what the 
        minimum viable level of documentation here should be.</p>

    </div>
  </div>
</section>