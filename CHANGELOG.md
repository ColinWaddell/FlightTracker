# Changelog

All notable changes to FlightTracker are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v2.1.3] - 2026-07-12

### Changed
- Settings UI refactored: categories now split into separate pages using Vue Router (hash mode), with a persistent sidebar and a Save button always visible at the bottom.
- All CSS across the web templates consolidated into a shared `style.css` file.
- All settings page JavaScript extracted into a dedicated `settings.js` file.

## [v2.1.2] - 2026-07-11

### Changed
- OSN now polls at maximum rate the free API will allow

## [v2.1.1] - 2026-07-11

### Changed
- Minor UI updates for the data-sources network.

### Fixed
- Cache is now cleared on update so stale entries never survive a version change.

## [v2.1.0] - 2026-07-11

### Added
- **OpenSky Network data source** - use OSN as an alternative to FlightRadar24, authenticated via OAuth2 client credentials (Client ID + Client Secret obtained from your OSN account). Configured from the web UI under Data Source.
- **adsbdb.com unified lookup** - route origin/destination and aircraft type are now both resolved via [adsbdb.com](https://api.adsbdb.com) for tar1090 and OpenSky Network data sources, replacing the previous mix of adsb.im (routes) and hexdb.io (aircraft type). Route and aircraft lookups are now independent, each cached under their own key with a 24-hour TTL.
- `python flight-tracker.py cache clear` CLI command to wipe all on-disk cache files (routes and TLE).
- Cache is automatically cleared on a successful OTA update so stale entries never survive a version change.

### Changed
- `data_source` config key now accepts `"osn"` in addition to `"fr24"` and `"tar1090"`.
- `route_lookup.py` rewritten to use two separate adsbdb endpoints (`/v0/callsign/{callsign}` for routes, `/v0/aircraft/{mode_s}` for aircraft type) rather than the combined endpoint, which silently omitted route data when adsbdb could not verify the callsign–airframe association.
- Stale cache entries with empty origin and destination are now treated as cache misses and re-queried, fixing cases where old backend data blocked fresh lookups.

### Fixed
- Origin and destination showing blank for flights whose routes were known to adsbdb via the callsign endpoint but not resolvable via the combined aircraft endpoint (e.g. KLM933 → AMS–DUB).
- Python 3.13 dummy-thread GC noise (`TypeError: 'NoneType' object does not support the context manager protocol`) eliminated by using persistent `requests.Session` objects in `route_lookup`, `overhead_tar1090`, and `overhead_osn`.

## [v2.0.7] - 2026-07-11

### Added
- Pytest test suite with 141 tests across 8 modules covering configuration migration, route caching, flight scene helpers, overhead data handling, CLI dispatch, satellite math, scene manager, and theme system
- `pyproject.toml` now includes `dev` optional dependencies (`pytest`, `pytest-cov`) and `[tool.pytest.ini_options]` configuration
- CI workflow expanded with a `test` job that installs dependencies and runs the full pytest suite
- GitHub issue templates (bug report with debug config export guidance, feature request linking to CONTRIBUTING.md)
- `SECURITY.md` with responsible disclosure guidance
- Ko-fi funding link in `.github/FUNDING.yml` and floating button on the gh-pages site
- `CHANGELOG.md` (Keep a Changelog format, covering v2.0.0 onward)

### Fixed
- Plane cache retrieval bugs where flights were not pulling out of cache correctly
- README license link corrected from `LICENSE` to `LICENSE.md`
- Ruff lint issues (42 auto-fixed, 11 manually fixed) across the codebase

### Changed
- LICENSE copyright year updated to 2026
- `.gitignore` updated with `node_modules/`, `_site/`, `.dev/`

## [v2.0.6] - 2026-07-11

### Changed
- Airport display options expanded from a simple full-name toggle to five styles: short code, full name, abbreviated name, municipality, and municipality + country
- Replaced `full_airport_name` and `abbreviate_name` config keys with a single `airport_display_style` setting (0–4)
- Bundled airports database significantly expanded (45,000+ entries) with richer metadata (name, municipality, country)
- Airport lookup now returns full airport info dict instead of just the name string, for both FR24 and tar1090 data sources

## [v2.0.5] - 2026-07-11

### Fixed
- Updater no longer blocked by untracked files (e.g. `.bak` files from config migration) - `git status` now uses `--untracked-files=no`

## [v2.0.4] - 2026-07-11

### Added
- Advanced flight zone mode: draw a bounding box on a map to define the search area instead of using a centre + radius
- Observer position setting (advanced mode) for weather, sunrise/sunset, satellite passes, and flight distance sorting
- Interactive map selector in the web UI for choosing between simple and advanced zone definitions

### Changed
- `flight_location_mode` config key added (`"simple"` or `"advanced"`)
- Web settings page reworked with map-based zone picker

## [v2.0.3] - 2026-07-11

### Added
- Satellite pass timeout: optionally limit how long the satellite scene is shown per pass, yielding back to flight tracking after a configurable number of seconds from acquisition of signal (AOS)
- `satellite_timeout_enabled` and `satellite_timeout_seconds` config keys
- Satellite timeout controls in the web UI

### Fixed
- Restored polling route for web UI status updates

## [v2.0.2] - 2026-07-09

Bundled the complete v2 overhaul (see [v2.0.0](#v200---2026-07-09)) along with several post-merge refinements.

### Added
- Password enforcement on first run
- CLI utilities (`config`, `data`, `reset-password`, `interface enable/disable`)
- Auto-update status reporting
- Documentation and README rewrite for the v2 branch structure

### Removed
- Old v1 scene files (`clock.py`, `date.py`, `day.py`, `flightdetails.py`, `journey.py`, `planedetails.py`, `weather.py`)
- `animator.py` (replaced by scene manager)
- Taps-aff weather service (replaced by WeatherAPI)

## [v2.0.1] - 2026-07-08

### Added
- Initial auto-update test release - verified the update mechanism works end-to-end from the web UI

## [v2.0.0] - 2026-07-09 - Overhaul released

Complete ground-up rewrite of FlightTracker, developed across `release/v2` and numerous feature/hotfix branches. Not separately tagged, but merged into `main` on 9 July 2026 and first released as v2.0.1.

### Added
- **Complete codebase rewrite** from the ground up, reorganised into `scenes/`, `display/`, `utilities/`, `setup/`, and `web/` packages
- **Scene manager architecture** (C++-style) with `on_enter`/`on_exit` lifecycle, making it straightforward to add new display scenes
- **Web configuration UI** with login page, password protection, settings editor, update page, and log viewer
- **Satellite tracking** - plot satellite passes with NORAD ID configuration, azimuth/elevation ring, and trajectory arcs
- **Idle screen** showing time, weather (temperature + optional 24-hour rainfall chart), date, and day
- **Splash screen** with custom bitmap logo and QR code for web UI access
- **Raspberry Pi 5 support** with dedicated installer, requirements, and `rgbpanel_piomatter` display driver
- **Desktop simulator** platform with `rgbpanel_simulator` for development without hardware
- **One-line install scripts** for Pi 3/4/Zero and Pi 5 with hardware detection, progress output, and systemd service setup
- **Auto-update system** - update from the web UI or CLI, with git pull, pip install, and service restart
- **CLI tools** - `config`, `data`, `reset-password`, `interface enable/disable`, `--version`
- **Structured logging** with configurable verbosity, accessible from the web UI
- **Brightness scheduling** based on sunrise/sunset, with configurable time windows and brightness levels
- **Themes** - default, monochrome, and pastel colour palettes
- **tar1090 / local ADS-B receiver support** as an alternative to FlightRadar24
- **adsbdb.com integration** for origin/destination airport lookups when using tar1090
- **Routes caching** to reduce repeated API calls
- **Loading LED** - optional GPIO LED that blinks while fetching flight data
- **Configurable airport display** - short code, full name, or abbreviated
- **Home airport highlighting** - emphasise your local IATA code on the display
- **Animation speed presets** - `default`, `slower`, `faster`
- **Callsign format selector** - ICAO callsign (e.g. BAW123) or IATA flight number (e.g. BA123), FR24 only
- **Rain sensitivity** setting for the rainfall chart
- **Imperial/metric units** toggle
- **24-hour/12-hour clock** and date format options
- **Screen rotation** (180°) and **brightness** controls (1–5)
- **Bundled airports database** (`airports.json`) with Python helper script to keep it updated

### Removed
- Old v1 scene files (`clock.py`, `date.py`, `day.py`, `flightdetails.py`, `journey.py`, `planedetails.py`, `weather.py`)
- `animator.py` (replaced by scene manager)
- Taps-aff weather service (replaced by WeatherAPI)

---

## v1

The original Python flight tracker for Raspberry Pi. Lives on the `master` branch.