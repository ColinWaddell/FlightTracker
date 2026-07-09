---
layout: base.njk
title: "What's that over my house?"
description: "A Raspberry Pi-powered RGB LED matrix that shows you what aircraft are overhead."
permalink: "/"
---

<section class="hero">
  <div class="container">
    <div class="row align-items-center g-4">
      <div class="col-lg-12">
          <div class="hero-headline">
            <h1>What's that <span class="yellow">over my house?</span></h1>
            <br />
            <img src="/images/logo.png" alt="{{ site.name }}" class="hero-logo pb-3" />
          </div>
      </div>
    </div>
    <div class="row align-items-center g-4">
      <div class="col-lg-12">
        <div class="hero-carousel" id="hero-carousel">
          <div class="hero-carousel-slides">
            <div class="hero-carousel-slide active" data-type="image">
              <img src="/images/blog/screen-flight.jpg" alt="FlightTracker showing a live flight on the LED matrix" />
            </div>
            <div class="hero-carousel-slide" data-type="video">
              <video autoplay loop muted playsinline preload="metadata" class="w-100 d-block">
                <source src="images/captures/pass-preview.mp4" type="video/mp4">
                <source src="images/captures/pass-preview.webm" type="video/webm">
              </video>
            </div>
            <div class="hero-carousel-slide" data-type="image">
              <img src="/images/blog/internals-in-case.jpg" alt="Inside the FlightTracker case showing the Raspberry Pi" />
            </div>
            <div class="hero-carousel-slide" data-type="video">
              <video autoplay loop muted playsinline preload="metadata" class="w-100 d-block">
                <source src="images/captures/satellite-pass.mp4" type="video/mp4">
                <source src="images/captures/satellite-pass.webm" type="video/webm">
              </video>
            </div>
          </div>
          <button class="hero-carousel-prev" aria-label="Previous slide">&lsaquo;</button>
          <button class="hero-carousel-next" aria-label="Next slide">&rsaquo;</button>
          <div class="hero-carousel-dots">
            <button class="hero-carousel-dot active" aria-label="Go to slide 1"></button>
            <button class="hero-carousel-dot" aria-label="Go to slide 2"></button>
            <button class="hero-carousel-dot" aria-label="Go to slide 3"></button>
            <button class="hero-carousel-dot" aria-label="Go to slide 4"></button>
          </div>
        </div>
      </div>
    </div>
    <div class="row align-items-center g-4">
      <div class="col-lg-12">
        <div class="hero-text mt-3">
          <p>A Raspberry Pi-powered RGB LED matrix that shows you what aircraft and satellites are overhead.</p>
          <p>FlightTracker takes live aircraft data, works out what is nearby, and displays it on a 64x32 RGB LED matrix. When there is nothing overhead, it can show the time, weather, temperature, rainfall, or satellite passes.</p>
          <p>This site will show you what you need to build your own and get the software installed.</p>
          <div class="hero-actions">
            <a href="/build/" class="btn btn-yellow me-sm-4"><span class="btn-label">Hardware</span><span class="btn-subtext">Build your own</span></a>
            <a href="/install/" class="btn btn-dark"><span class="btn-label">Software</span><span class="btn-subtext">Install and configure</span></a>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">What it does</h2>

    {% include "feature-grid.njk" %}
  </div>

</section>

<hr />

<section>
  <div class="container">
    <h2 class="section-title">Display modes</h2>
    <div class="narrative">
        <div>
        <p>FlightTracker has a few different ways of showing aircraft information.</p>
        <p>You can keep it simple and show the aircraft type and route, or switch to more telemetry-type data such as altitude, speed, and heading. Airport names can be shown in full or as three-letter codes.</p>
        </div>
    </div>

    {% include "display-modes.njk" %}
  </div>
</section>

<section>
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
        <video autoplay loop muted playsinline preload="metadata" class="w-100 d-block">
            <source src="images/captures/web-config-ui.mp4" type="video/mp4">
            <source src="images/captures/web-config-ui.webm" type="video/webm">
        </video>
      </div>
    </div>

    <div class="narrative">
      <p>On first boot, FlightTracker shows a QR code on the matrix. Scan it with your phone and configure it from there.</p>
    </div>

    <div class="card">
      <div class="card-body p-2 bg-black">
        <img src="images/captures/qr_code.png" alt="FlightTracker first boot QR code splash screen" loading="lazy" class="w-100 d-block">
      </div>
      <div class="card-header">First boot - scan to configure</div>
    </div>

  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">Themes</h2>

    <div class="narrative mb-4">
      <p>The theme system covers the full display, not just a few headline colours. Flight data, weather gradients, charts, labels, and idle screens all follow the selected theme.</p>
    </div>

    <div class="card mb-4">
      <div class="card-body p-2 bg-black">
        <video autoplay loop muted playsinline preload="metadata" class="w-100 d-block">
          <source src="images/captures/themes.mp4" type="video/mp4">
          <source src="images/captures/themes.webm" type="video/webm">
        </video>
      </div>
      <div class="card-header">Cycling through Default, Monochrome, and Pastel themes</div>
    </div>

    {% include "theme-swatches.njk" %}

    <div class="narrative mb-4">
      <p><em>Looking for a way to contribute? I'd love some help adding new themes.</em></p>
    </div>
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">Weather and idle display</h2>
    <div class="narrative">
      <p>Aircraft are not always overhead.</p>
      <p>When FlightTracker has nothing useful to say about aircraft, it can show the time, date, and temperature. With an OpenWeather API key, it can also show temperature and rainfall information.</p>
    </div>

    <div class="card">
      <div class="card-body p-2 bg-black">
        <img src="images/captures/idle-screen.png" alt="Idle screen - time, temperature, day and date" loading="lazy" class="w-100 d-block">
      </div>
      <div class="card-header">Idle screen - time, temperature, predicted rainfall, day and date</div>
    </div>

    <div class="narrative">
      <p>The screen can be configured to dim throughout the night or even switch off.</p>
    </div>
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">Satellite tracking</h2>
    <div class="narrative">
      <p>FlightTracker can also show satellite passes on an azimuth/elevation plot.</p>
      <p>It fetches <a href="https://en.wikipedia.org/wiki/Two-line_element_set">TLE data</a> from CelesTrak and works out when satellites are overhead.</p>
    </div>

    <div class="card">
      <div class="card-body p-2 bg-black">
        <video autoplay loop muted playsinline preload="metadata" class="w-100 d-block">
          <source src="images/captures/satellite-pass.mp4" type="video/mp4">
          <source src="images/captures/satellite-pass.webm" type="video/webm">
        </video>
      </div>
      <div class="card-header">ISS pass - azimuth/elevation plot with speed and altitude</div>
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
      <div class="info-panel-header">tar1090 / dump1090</div>
      <div class="info-panel-body">
        <p>If you have your own ADS-B receiver, FlightTracker can use your local <code>tar1090</code> or <code>dump1090</code> instance instead.</p>
        <p>That means no API keys, no rate limits, and no relying on someone else's service if you already have the aircraft data yourself.</p>
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