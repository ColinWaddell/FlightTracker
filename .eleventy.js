// Eleventy configuration for the FlightTracker website.
// Content lives in src/ as Markdown + JSON data; output goes to _site/.

// The site is served from a subpath on GitHub Pages
// (https://colinwaddell.github.io/FlightTracker/). Locally it runs at the
// root, so all URLs in the content are root-absolute ("/css/...", "/images/...").
// This prefix is injected into the final HTML so the same source works in both
// environments. Set to "" to disable.
const PATH_PREFIX = "/FlightTracker";

module.exports = function (eleventyConfig) {
  // Pass through static assets unchanged.
  eleventyConfig.addPassthroughCopy("css");
  eleventyConfig.addPassthroughCopy("images");
  eleventyConfig.addPassthroughCopy("assets");

  // Rewrite root-absolute URLs (href="/...", src="/...") to include the
  // path prefix, so assets resolve correctly under the GitHub Pages subpath.
  // External URLs (//, http://, https://) and hash links (#...) are left alone.
  eleventyConfig.addTransform("path-prefix", function (content) {
    if (!PATH_PREFIX || !this.page.outputPath.endsWith(".html")) {
      return content;
    }
    return content.replace(
      /((?:href|src)\s*=\s*["'])\/(?!\/)/g,
      `$1${PATH_PREFIX}/`
    );
  });

  // Live-reload when CSS changes (passthrough copy doesn't trigger watch by default).
  eleventyConfig.addWatchTarget("css/");
  eleventyConfig.addWatchTarget("images/");

  // A small filter for inline code styling in Markdown.
  eleventyConfig.addFilter("inlineCode", (str) => {
    return `<code class="inline-code">${str}</code>`;
  });

  return {
    dir: {
      input: "src",
      includes: "_includes",
      layouts: "_layouts",
      data: "_data",
      output: "_site",
    },
    // Allow Nunjucks inside Markdown so we can drop in includes/shortcodes.
    markdownTemplateEngine: "njk",
    htmlTemplateEngine: "njk",
    templateFormats: ["md", "njk", "html"],
  };
};