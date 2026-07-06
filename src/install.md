---
layout: base.njk
title: "Get Started"
description: "Install FlightTracker on your Raspberry Pi in one line."
permalink: "/install/"
---

<section>
  <div class="container">
    <h2 class="section-title">Getting started</h2>

    <div class="narrative">
      <p>You've put everything together using the build instructions and now you're ready to install the software.</p>
    </div>
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">Quick install</h2>

    <div class="narrative">
        <div class="alert alert-warning border-warning border-2" role="alert">
            <p class="mb-0"><strong>If you know what you're doing</strong> and you've got a Raspberry Pi you can SSH into, and you're happy for the installer script to treat the system as a fresh install, then you can skip the rest of this page and just run:</p>
        </div>
    </div>

    <div class="code-card">
      <div class="code-card-header">
        <span>One-line installer</span>
        <button class="code-card-copy" onclick="copyCode(this, 'curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/feature/feature-upgrade/install.sh | bash')">Copy</button>
      </div>
      <div class="code-card-body">
        <pre><code>curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/feature/feature-upgrade/install.sh | bash</code></pre>
      </div>
    </div>

    <div class="narrative mt-3">
      <p>The script installs the RGB matrix driver, clones FlightTracker, sets up the Python environment, and configures a systemd service so it starts on boot. You can <a href="https://github.com/ColinWaddell/FlightTracker/blob/feature/feature-upgrade/install.sh">read the script on GitHub</a> before you run it.</p>
      <p>If you'd rather go step by step - or you're starting from scratch and need to prepare an SD card first - read on.</p>
    </div>
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">Preparing the SD card</h2>

    <div class="narrative">
      <p>The easiest way to get all the FlightTracker software installed is with a freshly prepared Raspberry Pi. The quick-installer script assumes it's running on a fresh install of Raspberry Pi OS, Trixie.</p>
      <p>These instructions are a walk-through of how to use the Raspberry Pi Imager for those unfamiliar with these tools.</p>

      <p>First, download and install <a href="https://www.raspberrypi.com/software/">Raspberry Pi Imager</a> on your computer.</p>

      <div class="alert alert-info border-info border-2" role="alert">
        <p class="mb-0">Use a decent quality microSD card with at least <strong>8GB</strong> of space. Cheap cards can cause random crashes, slow installs and have a higher chance of randomly dying.</p>
      </div>

      <p>Stick a microSD card into your computer and open the Imager. The steps are:</p>

      <ol>
        <li><strong>Choose your device</strong> - pick the Raspberry Pi model you're using (3B, 4B, Zero 2, Zero W, etc.).</li>
      </ol>

      <div class="card mb-3">
        <div class="card-header">Select your device</div>
        <div class="card-body p-2">
          <img src="/images/installer/001_select_your_device.png" alt="Raspberry Pi Imager device selection screen" loading="lazy" class="w-100 d-block">
        </div>
      </div>

      <ol start="2">
        <li><strong>Choose your OS</strong> - select <em>Raspberry Pi OS (Other)</em> and then <em>Raspberry Pi OS Lite</em>. The Lite version has no desktop environment, which is exactly what we want - FlightTracker runs headless and a desktop would just wastes resources. The Imager will show you the correct version for your device. If it offers you a choice between 32-bit and 64-bit, go with 32-bit if you're on a Pi Zero, otherwise go with 64-bit.</li>
      </ol>

      <div class="card mb-3">
        <div class="card-header">Choose your OS</div>
        <div class="card-body p-2">
          <img src="/images/installer/002_choose_os.png" alt="Raspberry Pi Imager OS selection screen showing Raspberry Pi OS Lite" loading="lazy" class="w-100 d-block">
        </div>
      </div>

      <ol start="3">
        <li><strong>Choose your storage</strong> - select your microSD card. Double-check you've picked the right one, because everything on it is about to be wiped.</li>
        <li><strong>Edit the settings</strong> - before you write, the Imager will offer to apply OS customisation settings. This is where you set up:
          <ul>
            <li>A <strong>hostname</strong> for your Pi (something like <code>flighttracker</code> makes it easy to find on your network).</li>
            <li>A <strong>username and password</strong> - you'll need these to SSH in later. The quick-installer assumes the username <code>pi</code>.</li>
          </ul>

          <div class="card mb-3">
            <div class="card-header">Set your username and password</div>
            <div class="card-body p-2">
              <img src="/images/installer/003_choose_username.png" alt="Raspberry Pi Imager OS customisation screen showing username and password fields" loading="lazy" class="w-100 d-block">
            </div>
          </div>

          <ul>
            <li><strong>SSH</strong> - under the Services tab, tick <em>Enable SSH</em> and choose <em>Use password authentication</em>. Unless you know what you're doing with SSH keys, password-based login is the simplest way to get going.</li>
            <li>Your <strong>Wi-Fi</strong> details, if you're not using a wired connection.</li>
          </ul>

          <div class="card mb-3">
            <div class="card-header">Configure Wi-Fi</div>
            <div class="card-body p-2">
              <img src="/images/installer/004_choose_wifi.png" alt="Raspberry Pi Imager OS customisation screen showing Wi-Fi configuration" loading="lazy" class="w-100 d-block">
            </div>
          </div>

          <ul>
            <li><strong>SSH</strong> - under the Services tab, tick <em>Enable SSH</em> and choose <em>Use password authentication</em>. Unless you know what you're doing with SSH keys, password-based login is the simplest way to get going.</li>
          </ul>

          <div class="card mb-3">
            <div class="card-header">Enable SSH</div>
            <div class="card-body p-2">
              <img src="/images/installer/005_ssh.png" alt="Raspberry Pi Imager Services tab showing SSH enabled with password authentication" loading="lazy" class="w-100 d-block">
            </div>
          </div>
        </li>
        <li><strong>Write</strong> - hit the button and wait. The Imager writes the image, verifies it, and applies your settings in one go.</li>
      </ol>

      <p>Once that's done, eject the card, slot it into your Pi, and power it on. Give it a minute or two to boot and join your network, then SSH in from your computer:</p>
    </div>

    <div class="code-card">
      <div class="code-card-header">
        <span>SSH into your Pi</span>
        <button class="code-card-copy" onclick="copyCode(this, 'ssh pi@flighttracker.local')">Copy</button>
      </div>
      <div class="code-card-body">
        <pre><code>ssh pi@flighttracker.local</code></pre>
      </div>
    </div>

    <div class="narrative">
      <p>If the <code>.local</code> hostname doesn't resolve on your network, you can find the Pi's IP address from your router's admin page and use that instead.</p>
    </div>
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">SSH in and run the installer</h2>

    <div class="narrative">
      <p>Now you need to connect to your Pi over SSH and run the installer script. If you've never used SSH before, it's a way to run commands on another computer over the network. The <a href="https://www.raspberrypi.com/documentation/computers/remote-access.html#ssh">Raspberry Pi SSH guide</a> covers installing an SSH client on Windows, macOS, and Linux.</p>

      <p>Open a terminal (or Command Prompt / PowerShell on Windows) and connect to your Pi using the username and hostname you set in the Imager:</p>
    </div>

    <div class="code-card">
      <div class="code-card-header">
        <span>Connect to your Pi</span>
        <button class="code-card-copy" onclick="copyCode(this, 'ssh pi@flighttracker.local')">Copy</button>
      </div>
      <div class="code-card-body">
        <pre><code>ssh pi@flighttracker.local</code></pre>
      </div>
    </div>

    <div class="narrative">
      <p>Accept the security prompt (type <code>yes</code> if it asks about a host key), then enter the password you set in the Imager. You won't see the characters as you type - that's normal for SSH.</p>

      <p>Once you're in, you'll be sitting at a prompt on the Pi. Now run the installer:</p>
    </div>

    <div class="code-card">
      <div class="code-card-header">
        <span>One-line installer</span>
        <button class="code-card-copy" onclick="copyCode(this, 'curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/feature/feature-upgrade/install.sh | bash')">Copy</button>
      </div>
      <div class="code-card-body">
        <pre><code>curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/feature/feature-upgrade/install.sh | bash</code></pre>
      </div>
    </div>

    <div class="narrative">
      <p>The script will walk through the whole install: the RGB matrix driver, the FlightTracker code, the Python environment, and a systemd service so it starts automatically on boot. This can take any where from a few minutes on newer systems to half an hour or so on older models of Pi</p>

      <p>When it's done, the Pi will reboot and FlightTracker will start up. The first time this boots it can take a few minutes before everything is running. If you're concerned something isn't right you can ssh in and execute <code>sudo systemctl status FlightTracker.service</code> to see what's going on.</p>

      <p>On boot he FlightTracker shows a QR code on the matrix - you can scan it with your phone to open the web configuration UI. You can also access the settings directly in a browser at <code>http://flighttracker.local:8584</code> (using the hostname you set in the Imager) or <code>http://&lt;your-pi-ip&gt;:8584</code> (using the Pi's IP address). From there you can setup your device.</p>

      <div class="card">
        <div class="card-body p-2 bg-black">
            <img src="../images/captures/qr_code.png" alt="FlightTracker first boot QR code splash screen" loading="lazy" class="w-100 d-block">
        </div>
       <div class="card-header">First boot - scan to configure</div>
      </div>

      <p>If anything goes wrong, the full manual install steps are in the <a href="https://github.com/ColinWaddell/FlightTracker#installation">README on GitHub</a>, and you can <a href="https://github.com/ColinWaddell/FlightTracker/issues">raise an issue</a> if you get stuck.</p>
    </div>
  </div>
</section>