---
layout: base.njk
title: "FlightTracker - Raspberry Pi Flight Tracker"
description: "A Raspberry Pi-powered RGB LED matrix that shows you what aircraft and satellites are overhead. Build your own with FlightTracker OS - no command line required."
permalink: "/"
og_type: "website"
og_title: "Raspberry Pi Flight Tracker"
og_image: "/images/carousel/flight-tracker-01.jpg"
structured_data: |
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "FlightTracker",
    "operatingSystem": "Raspberry Pi OS",
    "applicationCategory": "MakerApplication",
    "description": "A Raspberry Pi-powered RGB LED matrix that shows you what aircraft and satellites are overhead.",
    "url": "https://flight-tracker.dev/",
    "downloadUrl": "https://github.com/ColinWaddell/FlightTracker",
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
    "image": "https://flight-tracker.dev/images/carousel/flight-tracker-01.jpg"
  }
---

<section class="hero border-bottom">
  <div class="container">
    <div class="row align-items-center g-4 hero-headline">
      <div class="col-12 col-lg-9">
        <h1>FlightTracker<br/><span class="yellow">What's that up there?</span></h1>
      </div>
      <div class="col-12 col-lg-3 text-lg-end">
        <img src="/images/logo.png" alt="{{ site.name }}" class="hero-logo pb-3" />
      </div>
    </div>
    <div class="row align-items-center g-4">
      <div class="col-lg-12">
        <div class="hero-carousel" id="hero-carousel">
          <div class="hero-carousel-slides">
            <div class="hero-carousel-slide active" data-type="image">
              <img src="/images/carousel/flight-tracker-01.jpg" alt="FlightTracker displaying live aircraft data on an RGB LED matrix" />
            </div>
            <div class="hero-carousel-slide" data-type="image">
              <img src="/images/carousel/flight-tracker-02.jpg" alt="FlightTracker showing the idle weather screen on an RGB LED matrix" />
            </div>
          </div>
          <button class="hero-carousel-prev" aria-label="Previous slide">&lsaquo;</button>
          <button class="hero-carousel-next" aria-label="Next slide">&rsaquo;</button>
          <div class="hero-carousel-dots">
            <button class="hero-carousel-dot active" aria-label="Go to slide 1"></button>
            <button class="hero-carousel-dot" aria-label="Go to slide 2"></button>
          </div>
        </div>
      </div>
    </div>
    <div class="row align-items-center g-4">
      <div class="col-lg-12">
        <div class="hero-text mt-3">
          <p>A Raspberry Pi-powered RGB LED matrix that shows you what aircraft and satellites are overhead.</p>
          <p>FlightTracker takes live aircraft data, works out what is nearby, and displays it on a 64x32 RGB LED matrix. When there is nothing overhead, it can show the time, weather, temperature, rainfall, or satellite passes.</p>
          <p>This site will show you what you need to build your own and get the software installed. An <a href="https://www.printables.com/model/1820229-flight-tracker-screen-for-raspberry-pi-any-model-6" target="_blank">official 3D-printable case</a> is also available - see the build page for details.</p>
          <div class="hero-actions">
            <a href="/build/" class="btn btn-yellow me-sm-3"><span class="btn-label">Hardware</span><span class="btn-subtext">Build your own</span></a>
            <a href="/os/" class="btn btn-orange me-sm-3"><span class="btn-label">FlightTracker OS</span><span class="btn-subtext">No command line required</span></a>
            <a href="/install/" class="btn btn-dark"><span class="btn-label">Software</span><span class="btn-subtext">Install and configure</span></a>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="border-bottom">
  <div class="container">
    <h2 class="section-title">FlightTracker OS</h2>

    <div class="row g-4">
      <div class="col-lg-7">
        <div class="narrative">
          <p>FlightTracker OS is a pre-built Raspberry Pi image that has everything installed and configured for you - no command line required.</p>
          <p>Flash it to an SD card with <a href="https://www.raspberrypi.com/software/" target="_blank">Raspberry Pi Imager</a>, set your Wi-Fi details, flash, and boot.
          You can then log into the web installer and finish setup from your browser.</p>
          <p>32-bit and 64-bit images are available for Raspberry Pi 3, 4, and 5.</p>
          <p><a href="/os/">Find out more about FlightTracker OS →</a></p>
        </div>
        <div class="rpi-imager-btn-wrap mt-3">
          <a class="btn btn-rpi" href="rpi-imager://open?repo=https%3A%2F%2Fraw.githubusercontent.com%2FColinWaddell%2FFlightTracker-Image%2Frefs%2Fheads%2Fmain%2Fos_list.json">
            <img src="/images/Raspberry_Pi_Logo.svg" width="40">Click To Install With Raspberry Pi Imager
          </a>
        </div>
      </div>
      <div class="col-lg-5">
        <div class="card">
          <div class="card-header">The FlightTracker OS web installer</div>
          <div class="card-body p-2">
            <img src="/images/installer/web-installer.png" alt="FlightTracker OS web installer" loading="lazy" class="w-100 d-block">
          </div>
        </div>
      </div>
    </div>
  </div>

</section>

<section class="border-bottom">
  <div class="container">
    <h2 class="section-title">What it does</h2>

    {% include "feature-grid.njk" %}
  </div>

</section>

<section class="border-bottom">
  <div class="container">
    <h2 class="section-title">Display modes</h2>
    <div class="narrative">
        <p>FlightTracker has a few different ways of showing aircraft information.</p>
        <p>You can keep it simple and show the aircraft type and route, or switch to more telemetry-type data such as altitude, speed, and heading. Airport names can be shown in full or as three-letter codes along with the airline logo.</p>
    </div>
    {% include "display-modes.njk" %}
  </div>
</section>

<section class="border-bottom">
  <div class="container">
    <h2 class="section-title">Web configuration</h2>
    <div class="narrative">
        <p class="section-sub">FlightTracker includes a built-in web interface, no need to write any code to setup or configure.</p>
    </div>

    <div class="row">
      <div class="col-lg-4">
        <div class="card">
            <div class="card-header">
                From the web UI you can:
            </div>
            <ul class="list-group list-group-flush">
                    <li class="list-group-item">Set your location on a map</li>
                    <li class="list-group-item">Choose a display theme</li>
                    <li class="list-group-item">Adjust brightness</li>
                    <li class="list-group-item">Configure flight display options</li>
                    <li class="list-group-item">Set airport name behaviour</li>
                    <li class="list-group-item">Add an OpenWeather API key</li>
                    <li class="list-group-item">Configure ADS-B / tar1090 settings</li>
                    <li class="list-group-item">View live logs</li>
            </ul>
        </div>
      </div>
      <div class="col-lg-8">
        <div class="card">
          <div class="card-header">The web configuration interface</div>
          <div class="card-body p-2 bg-black">
            <video autoplay loop muted playsinline preload="metadata" class="w-100 d-block">
                <source src="/images/captures/web-config-ui.mp4" type="video/mp4">
                <source src="/images/captures/web-config-ui.webm" type="video/webm">
            </video>
          </div>
        </div>
      </div>
    </div>

    <div class="narrative">
      <p>On first boot, FlightTracker shows a QR code on the matrix. Scan it with your phone and configure it from there.</p>
    </div>

    <div class="card">
      <div class="card-header">First boot - scan to configure</div>
      <div class="card-body p-2 bg-black">
        <img src="/images/captures/qr_code.png" alt="FlightTracker first boot QR code splash screen" loading="lazy" class="w-100 d-block">
      </div>
    </div>

  </div>
</section>

<section class="border-bottom">
  <div class="container">
    <h2 class="section-title">Themes</h2>

    <div class="narrative mb-4">
      <p>The theme system covers the full display, not just a few headline colours. Flight data, weather gradients, charts, labels, and idle screens all follow the selected theme.</p>
    </div>

    <div class="card mb-4">
      <div class="card-header">Cycling through Default, Monochrome, and Pastel themes</div>
      <div class="card-body p-2 bg-black">
        <video autoplay loop muted playsinline preload="metadata" class="w-100 d-block">
          <source src="/images/captures/themes.mp4" type="video/mp4">
          <source src="/images/captures/themes.webm" type="video/webm">
        </video>
      </div>
    </div>

    {% include "theme-swatches.njk" %}

    <div class="narrative mb-4">
      <p><em>Looking for a way to contribute? I'd love some help adding new themes.</em></p>
    </div>
  </div>
</section>

<section class="border-bottom">
  <div class="container">
    <h2 class="section-title">Weather and idle display</h2>
    <div class="narrative">
      <p>Aircraft are not always overhead.</p>
      <p>When FlightTracker has nothing useful to say about aircraft, it can show the time, date, and temperature. With an OpenWeather API key, it can also show temperature, humidity, rainfall and forecast animations.</p>
    </div>

    <div class="card">
      <div class="card-header">Idle screen - time, temperature, predicted rainfall, day and date</div>
      <div class="card-body p-2 bg-black">
        <img src="/images/captures/forecast.png" alt="Idle screen - time, temperature, day and date" loading="lazy" class="w-100 d-block">
      </div>
    </div>

    <div class="narrative">
      <p>The screen can be configured to dim throughout the night or even switch off.</p>
    </div>
  </div>
</section>

<section class="border-bottom">
  <div class="container">
    <h2 class="section-title">Satellite tracking</h2>
    <div class="narrative">
      <p>FlightTracker can also show satellite passes on an azimuth/elevation plot.</p>
      <p>It fetches <a href="https://en.wikipedia.org/wiki/Two-line_element_set">TLE data</a> from CelesTrak and works out when satellites are overhead.</p>
    </div>

    <div class="card">
      <div class="card-header">ISS pass - azimuth/elevation plot with speed and altitude</div>
      <div class="card-body p-2 bg-black">
        <video autoplay loop muted playsinline preload="metadata" class="w-100 d-block">
          <source src="/images/captures/satellite-pass.mp4" type="video/mp4">
          <source src="/images/captures/satellite-pass.webm" type="video/webm">
        </video>
      </div>
    </div>
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">Data sources</h2>
    <p class="section-sub">FlightTracker can use a few different sources depending on how you want to run it.</p>

    <div class="info-panel">
      <div class="info-panel-header">FlightRadar24</div>
      <div class="info-panel-body">
        <p>The default setup uses FlightRadar24 data to find aircraft near your location.</p>
      </div>
    </div>

    <div class="info-panel">
      <div class="info-panel-header">Open Sky Network + ADSB.DB</div>
      <div class="info-panel-body">
        <p>If you register an account and obtain an <a href="https://opensky-network.org" target="_blank">OpenSky Network</a> API key, FlightTracker can use <a href="https://opensky-network.org" target="_blank">OpenSky Network</a> together with <a href="https://adsbdb.com" target="_blank">ADSB.DB</a> for flight, route, and aircraft lookups.</p>
      </div>
    </div>

    <div class="info-panel">
      <div class="info-panel-header">tar1090 / dump1090</div>
      <div class="info-panel-body">
        <p>If you have your own ADS-B receiver, FlightTracker can use your local <code>tar1090</code> or <code>dump1090</code> instance instead.</p>
        <p>That means no API keys, no rate limits, and no relying on someone else's service if you already have the aircraft data yourself.</p>
      </div>
    </div>

    <div class="info-panel">
      <div class="info-panel-header">hexdb.io</div>
      <div class="info-panel-body">
        <p>FlightTracker uses <a href="https://hexdb.io" target="_blank">hexdb.io</a> to look up flight routes (origin and destination airports) and aircraft type information by callsign and Mode-S hex code.</p>
        <p>Lookups are cached for 24 hours, keeping API usage low during normal operation.</p>
      </div>
    </div>

    <div class="info-panel">
      <div class="info-panel-header">CelesTrak</div>
      <div class="info-panel-body">
        <p>FlightTracker can also fetch TLE data from CelesTrak and use it to show satellite passes.</p>
        <p>The ISS and other satellites in your tracking list appear automatically when they are above your horizon.</p>
      </div>
    </div>

    <div class="info-panel">
      <div class="info-panel-header">What next?</div>
      <div class="info-panel-body">
        <p>Thanks to the big <code>version 2.0.0</code> rewrite it's going to be simple to add boats, trains, and who knows what else.</p>
        <p><a href="https://github.com/ColinWaddell/FlightTracker/issues" target="_blank">I'm open to suggestions</a></p>
      </div>
    </div>

    <!-- TODO: Write the "What's new in 2.0" callout summarising the rewrite - scene manager, web config UI, theme system, tar1090/ADS-B support, satellite tracking, config.json migration, logging. -->
  </div>
</section>

<script>
  (function () {
    var carousel = document.getElementById('hero-carousel');
    if (!carousel) return;
    var slides = carousel.querySelectorAll('.hero-carousel-slide');
    var dots = carousel.querySelectorAll('.hero-carousel-dot');
    var prev = carousel.querySelector('.hero-carousel-prev');
    var next = carousel.querySelector('.hero-carousel-next');
    var current = 0;
    var autoTimer = null;
    var AUTO_INTERVAL = 5000;

    function show(index) {
      // Pause any video in the outgoing slide
      var oldVideo = slides[current].querySelector('video');
      if (oldVideo) oldVideo.pause();

      slides[current].classList.remove('active');
      dots[current].classList.remove('active');
      current = (index + slides.length) % slides.length;
      slides[current].classList.add('active');
      dots[current].classList.add('active');

      // Play video if the new slide has one
      var newVideo = slides[current].querySelector('video');
      if (newVideo) {
        newVideo.currentTime = 0;
        newVideo.play().catch(function() {});
      }
    }

    function nextSlide() { show(current + 1); }
    function prevSlide() { show(current - 1); }

    function restartAuto() {
      clearInterval(autoTimer);
      autoTimer = setInterval(nextSlide, AUTO_INTERVAL);
    }

    prev.addEventListener('click', function () { prevSlide(); restartAuto(); });
    next.addEventListener('click', function () { nextSlide(); restartAuto(); });
    dots.forEach(function (dot, i) {
      dot.addEventListener('click', function () { show(i); restartAuto(); });
    });

    restartAuto();
  })();
</script>