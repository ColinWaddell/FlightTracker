---
layout: base.njk
title: "Get Started"
description: "Install FlightTracker on your Raspberry Pi in one line."
permalink: "/install/"
---

<div class="status-bar">
  <div class="status-item"><a href="#quick-install" class="text-black">Quick install</a></div>
  <div class="status-item"><a href="#full-install" class="text-black">Full install</a></div>
  <div class="status-item"><a href="#upgrading" class="text-black">Upgrading</a></div>
  <div class="status-item"><a href="#manual-install" class="text-black">Manual install</a></div>
  <div class="status-item"><a href="#simulator" class="text-black">Simulator</a></div>
</div>

<section>
  <div class="container">
    <h2 class="section-title">Getting started</h2>

    <div class="narrative">
      <p>You've put everything together using the build instructions and now you're ready to install the software.</p>
    </div>
  </div>
</section>

<section id="quick-install">
  <div class="container">
    <h2 class="section-title">Quick install</h2>

    <div class="narrative">
        <div class="alert alert-warning border-warning border-2" role="alert">
            <p class="mb-0"><strong>If you know what you're doing</strong> and you've got a Raspberry Pi you can SSH into, and you're happy for the installer script to treat the system as a fresh install, then you can skip the rest of this page. Pick the script for your hardware and run it:</p>
        </div>
    </div>

    <div class="code-card">
      <div class="code-card-header">
        <span>Raspberry Pi 3 / 4 / Zero</span>
        <button class="code-card-copy" onclick="copyCode(this, 'curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/release/v2/platforms/pi/install.sh | bash')">Copy</button>
      </div>
      <div class="code-card-body">
        <pre><code>curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/release/v2/platforms/pi/install.sh | bash</code></pre>
      </div>
    </div>

    <div class="code-card mt-2">
      <div class="code-card-header">
        <span>Raspberry Pi 5</span>
        <button class="code-card-copy" onclick="copyCode(this, 'curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/release/v2/platforms/pi5/install.sh | bash')">Copy</button>
      </div>
      <div class="code-card-body">
        <pre><code>curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/release/v2/platforms/pi5/install.sh | bash</code></pre>
      </div>
    </div>

    <div class="narrative mt-3">
      <p>Each script installs the appropriate RGB matrix driver for your hardware, clones FlightTracker, sets up the Python environment, and configures a systemd service so it starts on boot. Not sure which Pi you have? Run the Pi 3/4/Zero script - it will detect a Pi 5 and redirect you. You can read the scripts on GitHub before running them: <a href="https://github.com/ColinWaddell/FlightTracker/blob/release/v2/platforms/pi/install.sh">Pi 3/4/Zero</a> · <a href="https://github.com/ColinWaddell/FlightTracker/blob/release/v2/platforms/pi5/install.sh">Pi 5</a>.</p>
      <p>If you'd rather go step by step - or you're starting from scratch and need to prepare an SD card first - read on.</p>
    </div>
  </div>
</section>

<section id="full-install">
  <div class="container">
    <h2 class="section-title">Preparing the SD card</h2>

    <div class="narrative">
      <p>The easiest way to get all the FlightTracker software installed is with a freshly prepared Raspberry Pi. The installer script assumes it's running on a fresh install of Raspberry Pi OS Trixie.</p>
      <p>These instructions are a walk-through of how to use the Raspberry Pi Imager for those unfamiliar with these tools.</p>

      <p>First, download and install <a href="https://www.raspberrypi.com/software/">Raspberry Pi Imager</a> on your computer.</p>

      <div class="alert alert-info border-info border-2" role="alert">
        <p class="mb-0">Use a decent quality microSD card with at least <strong>8GB</strong> of space. Cheap cards can cause random crashes and slow installs, and they have a higher chance of randomly dying.</p>
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
        <li><strong>Choose your OS</strong> - select <em>Raspberry Pi OS (Other)</em> and then <em>Raspberry Pi OS Lite</em>. The Lite version has no desktop environment, which is exactly what we want - FlightTracker runs headless and a desktop would just waste resources. The Imager will show you the correct version for your device. If it offers you a choice between 32-bit and 64-bit, go with 64-bit unless you're on a Pi Zero, in which case choose 32-bit.</li>
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
        <span>Raspberry Pi 3 / 4 / Zero</span>
        <button class="code-card-copy" onclick="copyCode(this, 'curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/release/v2/platforms/pi/install.sh | bash')">Copy</button>
      </div>
      <div class="code-card-body">
        <pre><code>curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/release/v2/platforms/pi/install.sh | bash</code></pre>
      </div>
    </div>

    <div class="code-card mt-2">
      <div class="code-card-header">
        <span>Raspberry Pi 5</span>
        <button class="code-card-copy" onclick="copyCode(this, 'curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/release/v2/platforms/pi5/install.sh | bash')">Copy</button>
      </div>
      <div class="code-card-body">
        <pre><code>curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/release/v2/platforms/pi5/install.sh | bash</code></pre>
      </div>
    </div>

    <div class="narrative">
      <p>The script walks through the whole install: the RGB matrix driver appropriate for your hardware, the FlightTracker code, the Python environment, and a systemd service so it starts automatically on boot. This can take anywhere from a few minutes on newer systems to half an hour or so on older Pi models.</p>

      <p>When it's done, the Pi will reboot and FlightTracker will start up. The first boot can take a few minutes before everything is running. If you're concerned something isn't right, SSH in and run <code>sudo systemctl status FlightTracker.service</code> to see what's going on.</p>

      <p>On boot, FlightTracker shows a QR code on the matrix - scan it with your phone to open the web configuration UI. You can also access the settings directly in a browser at <code>http://flighttracker.local:8584</code> (using the hostname you set in the Imager) or <code>http://&lt;your-pi-ip&gt;:8584</code>.</p>

      <div class="card">
        <div class="card-body p-2 bg-black">
            <img src="../images/captures/qr_code.png" alt="FlightTracker first boot QR code splash screen" loading="lazy" class="w-100 d-block">
        </div>
       <div class="card-header">First boot - scan to configure</div>
      </div>

      <p>If anything goes wrong, the manual install steps are in the platform-specific folders on GitHub: <a href="https://github.com/ColinWaddell/FlightTracker/tree/release/v2/platforms/pi"><code>platforms/pi</code></a> and <a href="https://github.com/ColinWaddell/FlightTracker/tree/release/v2/platforms/pi5"><code>platforms/pi5</code></a>. You can also <a href="https://github.com/ColinWaddell/FlightTracker/issues">raise an issue</a> if you get stuck.</p>
    </div>


    <div class="narrative">
        <hr />
      <h2 class="section-title" id="upgrading">Upgrading from FlightTracker v1 to v2</h2>

      <p>
        I'd recommend a clean install by wiping your SD card and starting from scratch. If that's not an option, you should be able to stop the current code from running and swap out the source code
        for the latest version.
      </p>

      <p>
        If you've customised the code, you're probably going to have a bad time trying to update in place,
        as a huge amount has been rewritten between v1 and v2.
      </p>

      <p>
        If you've got a clear path to upgrade then the code will port across your <code>config.py</code>
        to a <code>config.json</code> automatically on the first boot.
      </p>

      <p>Before proceeding make sure you stop the FlightTracker from running:</p>

      <div class="code-card">
        <div class="code-card-header">
          <span>Stop the running service</span>
          <button class="code-card-copy" onclick="copyCode(this, 'sudo systemctl stop FlightTracker.service')">Copy</button>
        </div>
        <div class="code-card-body">
          <pre><code>sudo systemctl stop FlightTracker.service</code></pre>
        </div>
      </div>

      <h3>You installed the original from a zip file</h3>

      <p>
        If you originally downloaded FlightTracker as a zip file from GitHub and extracted it into
        <code>/home/pi/FlightTracker</code>, the folder won't be a git repository so you can't pull
        updates. The cleanest approach is to remove the old source code and clone the latest version
        in its place.
      </p>

      <p>
        Since the folder isn't a git repository you can't pull updates, but you can swap out the
        source code by hand while keeping your existing virtual environment and settings. Back up
        your <code>config.py</code>, clear out everything except the <code>env</code> directory,
        drop in the latest source from GitHub, refresh the dependencies, restore your config and
        restart the service:
      </p>

      <div class="code-card">
        <div class="code-card-header">
          <span>Update from a zip download, preserving settings</span>
          <button class="code-card-copy" onclick="copyCode(this, 'cp /home/pi/FlightTracker/config.py /tmp/config.py.backup\n\ncd /home/pi/FlightTracker\nfind . -maxdepth 1 -not -name \'env\' -not -name \'.\' -exec rm -rf {} +\n\ncurl -sSL https://github.com/ColinWaddell/FlightTracker/archive/refs/heads/release/v2.zip -o /tmp/FlightTracker.zip\nunzip -q /tmp/FlightTracker.zip -d /tmp/FlightTracker-src\ncp -r /tmp/FlightTracker-src/FlightTracker-release-v2/. /home/pi/FlightTracker/\n\nsource env/bin/activate\npip install -r requirements.txt\n\ncp /tmp/config.py.backup /home/pi/FlightTracker/config.py\n\nsudo systemctl restart FlightTracker.service')">Copy</button>
        </div>
        <div class="code-card-body">
          <pre><code>cp /home/pi/FlightTracker/config.py /tmp/config.py.backup

cd /home/pi/FlightTracker
find . -maxdepth 1 -not -name 'env' -not -name '.' -exec rm -rf {} +

curl -sSL https://github.com/ColinWaddell/FlightTracker/archive/refs/heads/release/v2.zip -o /tmp/FlightTracker.zip
unzip -q /tmp/FlightTracker.zip -d /tmp/FlightTracker-src
cp -r /tmp/FlightTracker-src/FlightTracker-release-v2/. /home/pi/FlightTracker/

source env/bin/activate
pip install -r requirements.txt

cp /tmp/config.py.backup /home/pi/FlightTracker/config.py

sudo systemctl restart FlightTracker.service</code></pre>
        </div>
      </div>

      <p>
        On first boot the new code will port your <code>config.py</code> across to a
        <code>config.json</code> automatically.
      </p>

      <h3>You installed the original using git clone</h3>

      <p>
        If you originally cloned the repository with <code>git clone</code>, upgrading is
        straightforward. Move into your existing checkout and pull down the latest changes:
      </p>

      <div class="code-card">
        <div class="code-card-header">
          <span>Pull the latest code</span>
          <button class="code-card-copy" onclick="copyCode(this, 'cd /home/pi/FlightTracker\ngit fetch --all\ngit checkout release/v2\ngit pull')">Copy</button>
        </div>
        <div class="code-card-body">
          <pre><code>cd /home/pi/FlightTracker
git fetch --all
git checkout release/v2
git pull</code></pre>
        </div>
      </div>

      <p>
        If you have local modifications, the <code>git pull</code> may complain about conflicts. Stash
        your changes first, pull, then decide whether you still need them - remember a huge amount has
        been rewritten between v1 and v2:
      </p>

      <div class="code-card">
        <div class="code-card-header">
          <span>Stash local changes before pulling</span>
          <button class="code-card-copy" onclick="copyCode(this, 'cd /home/pi/FlightTracker\ngit stash\ngit checkout release/v2\ngit pull')">Copy</button>
        </div>
        <div class="code-card-body">
          <pre><code>cd /home/pi/FlightTracker
git stash
git checkout release/v2
git pull</code></pre>
        </div>
      </div>

      <p>
        Your existing <code>config.py</code> sits at the top level of the checkout and won't be
        touched by the pull. Once the new code is in place, refresh the Python dependencies and
        reinstall the systemd service. On first boot your <code>config.py</code> will be migrated to
        <code>config.json</code> automatically.
      </p>

      <div class="code-card">
        <div class="code-card-header">
          <span>Refresh dependencies and reinstall the service</span>
          <button class="code-card-copy" onclick="copyCode(this, 'cd /home/pi/FlightTracker\nsource env/bin/activate\npip install -r platforms/pi/requirements.txt\n\nsudo systemctl restart FlightTracker.service')">Copy</button>
        </div>
        <div class="code-card-body">
          <pre><code>cd /home/pi/FlightTracker
source env/bin/activate
pip install -r requirements.txt

sudo systemctl restart FlightTracker.service</code></pre>
        </div>
      </div>

    </div>

  </div>
</section>
<section id="simulator">
  <div class="container">
    <h2 class="section-title">Running the simulator</h2>

    <div class="narrative">
      <p>
        If you don't have a Raspberry Pi or LED panel handy, FlightTracker can run entirely on your
        desktop or laptop. When the hardware display drivers (piomatter for Pi 5, rgbmatrix for
        Pi 3/4) aren't available, the app automatically falls back to a pygame-based simulator that
        renders the LED matrix in a window on your screen.
      </p>

      <p>
        This is useful for development, testing configuration changes, or just seeing what the
        software looks like before you commit to building the full hardware.
      </p>

      <h3>Setup</h3>

      <p>
        You'll need Python 3.10 or newer. Clone the repo, create a virtual environment, and install
        the simulator dependencies:
      </p>

      <div class="code-card">
        <div class="code-card-header">
          <span>Linux / macOS</span>
          <button class="code-card-copy" onclick="copyCode(this, 'git clone https://github.com/ColinWaddell/FlightTracker\ncd FlightTracker\npython3 -m venv env\nsource env/bin/activate\npip install -r platforms/simulator/requirements.txt')">Copy</button>
        </div>
        <div class="code-card-body">
          <pre><code>git clone https://github.com/ColinWaddell/FlightTracker
cd FlightTracker
python3 -m venv env
source env/bin/activate
pip install -r platforms/simulator/requirements.txt</code></pre>
        </div>
      </div>

      <div class="code-card mt-2">
        <div class="code-card-header">
          <span>Windows</span>
          <button class="code-card-copy" onclick="copyCode(this, 'git clone https://github.com/ColinWaddell/FlightTracker\ncd FlightTracker\npython -m venv env\nenv\\Scripts\\activate\npip install -r platforms/simulator/requirements.txt')">Copy</button>
        </div>
        <div class="code-card-body">
          <pre><code>git clone https://github.com/ColinWaddell/FlightTracker
cd FlightTracker
python -m venv env
env\Scripts\activate
pip install -r platforms/simulator/requirements.txt</code></pre>
        </div>
      </div>

      <h3>Running</h3>

      <p>
        Launch it the same way you would on a Pi:
      </p>

      <div class="code-card">
        <div class="code-card-header">
          <span>Linux / macOS</span>
          <button class="code-card-copy" onclick="copyCode(this, 'env/bin/python3 flight-tracker.py')">Copy</button>
        </div>
        <div class="code-card-body">
          <pre><code>env/bin/python3 flight-tracker.py</code></pre>
        </div>
      </div>

      <div class="code-card mt-2">
        <div class="code-card-header">
          <span>Windows</span>
          <button class="code-card-copy" onclick="copyCode(this, 'env\Scripts\python.exe flight-tracker.py')">Copy</button>
        </div>
        <div class="code-card-body">
          <pre><code>env\Scripts\python.exe flight-tracker.py</code></pre>
        </div>
      </div>

      <p>
        A pygame window opens showing the simulated LED matrix. The app runs exactly as it would on
        a Pi, including the web configuration interface at
        <a href="http://localhost:8584"><code>http://localhost:8584</code></a>.
      </p>

      <h3>Capture keys</h3>

      <p>
        The simulator supports saving screenshots and video frame sequences — handy for creating
        the kind of capture clips you see on the home page:
      </p>

      <ul>
        <li><strong>P</strong> — Save a photo to <code>captures/</code></li>
        <li><strong>R</strong> — Toggle video recording on/off (saves a PNG frame sequence to <code>captures/</code>)</li>
      </ul>

      <p>
        Full setup details are in the
        <a href="https://github.com/ColinWaddell/FlightTracker/blob/release/v2/platforms/simulator/INSTALL.md">simulator install guide</a>
        on GitHub.
      </p>
    </div>
  </div>
</section>
