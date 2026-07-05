// Eleventy configuration for the FlightTracker website.
// Content lives in src/ as Markdown + JSON data; output goes to _site/.

module.exports = function (eleventyConfig) {
  // Pass through static assets unchanged.
  eleventyConfig.addPassthroughCopy("css");
  eleventyConfig.addPassthroughCopy("images");
  eleventyConfig.addPassthroughCopy("assets");

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