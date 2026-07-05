# FlightTracker Website

The marketing and getting-started site for [FlightTracker](https://github.com/ColinWaddell/FlightTracker), built with [Eleventy](https://www.11ty.dev/).

## Quick start

```bash
npm install
npm run serve
```

The site is at <http://localhost:8080> with live reload on save.

## Scripts

| Command           | What it does                              |
| ----------------- | ----------------------------------------- |
| `npm run serve`   | Dev server with live reload (port 8080)   |
| `npm run build`   | Production build to `_site/`              |
| `npm run clean`   | Remove `_site/`                           |
| `npm run debug`   | Serve with Eleventy debug output          |

## Structure

```
src/
  index.md          Intro / landing page
  features.md       What it does
  build.md          The hardware build story
  buy.md            Things to buy
  install.md        How to install (curl | bash)
  _data/            JSON data (features, hardware, timeline, themes, etc.)
  _includes/        Reusable Nunjucks partials (nav, footer, grids, panels)
  _layouts/         base.njk - the page shell
css/                Stylesheet (kept from the original site)
images/             Static images and captures
.eleventy.js        Build config
.github/workflows/  Deploy workflow (builds and pushes to GitHub Pages)
```

## Content model

- **Prose** lives in Markdown (`.md`) - one file per page.
- **Structured data** (feature grids, hardware lists, timeline, theme swatches) lives in `src/_data/*.json` and is rendered by the includes in `src/_includes/`.
- **Layout** uses [Bootstrap 5](https://getbootstrap.com/) (grid, spacing, flex utilities) loaded via CDN, with a single `base.njk` page shell.
- **Style** is `css/style.css` - the airport-wayfinding theme (colours, panels, typography) layered on top of Bootstrap. Layout rules that Bootstrap now handles have been removed.

## Deploy

Pushing to `main` triggers `.github/workflows/deploy.yml`, which builds the site and deploys it to GitHub Pages. In the repo settings, set **Settings → Pages → Source** to **GitHub Actions**.

## TODO markers

Unwritten content is marked with `TODO:` comments in the Markdown. Search for them with:

```bash
grep -rn "TODO:" src/
```

## The split from the README

This site is the **on-ramp** - the story, the build narrative, the friendly getting-started flow. The [FlightTracker README](https://github.com/ColinWaddell/FlightTracker) is the **reference** - what it does in one line, the full manual install, the config table, the license. The website's install page points to the README for the manual route.