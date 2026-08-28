// Eleventy configuration for the FlightTracker website.
// Content lives in src/ as Markdown + JSON data; output goes to _site/.

// The site is served from a custom domain (https://flight-tracker.dev/)
// at the root, so all URLs in the content are root-absolute ("/css/...", "/images/...").
// The path-prefix transform is kept for compatibility but is a no-op when
// SITE_PATH_PREFIX is unset (which is the default for both local and CI).
const PATH_PREFIX = process.env.SITE_PATH_PREFIX || "";

module.exports = function (eleventyConfig) {
  // Pass through static assets unchanged.
  eleventyConfig.addPassthroughCopy("css");
  eleventyConfig.addPassthroughCopy("images");
  eleventyConfig.addPassthroughCopy("assets");

  // Copy the root-level install.sh into _site/ so it's served at /install.sh
  eleventyConfig.addPassthroughCopy({ "install.sh": "install.sh" });
  eleventyConfig.addPassthroughCopy({ "robots.txt": "robots.txt" });

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