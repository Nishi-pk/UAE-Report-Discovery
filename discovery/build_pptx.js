// build_pptx.js — turns brief_content.json (from generate_brief.py) into an
// actual .pptx file in FCSC house style: navy/gold, Cambria headings.
//
// Usage: node build_pptx.js brief_content.json output.pptx

const pptxgen = require("pptxgenjs");
const fs = require("fs");

const [, , contentPath, outputPath] = process.argv;
if (!contentPath || !outputPath) {
  console.error("Usage: node build_pptx.js <content.json> <output.pptx>");
  process.exit(1);
}

const content = JSON.parse(fs.readFileSync(contentPath, "utf8"));

// ---- House style palette ----
const NAVY = "0A2540";
const GOLD = "B8912F";
const CREAM = "F7F5F0";
const INK = "1C2733";
const SLATE = "5B6675";
const WHITE = "FFFFFF";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3" x 7.5"

const FONT_HEAD = "Cambria";
const FONT_BODY = "Calibri";

// ---------------------------------------------------------------
// Slide 1 — Title
// ---------------------------------------------------------------
{
  const slide = pres.addSlide();
  slide.background = { color: NAVY };

  slide.addText("FCSC · COMPETITIVENESS TEAM", {
    x: 0.7, y: 0.6, w: 8, h: 0.4,
    fontFace: FONT_BODY, fontSize: 11, color: GOLD, bold: true, charSpacing: 2,
  });

  slide.addText(content.report_name || "Report Brief", {
    x: 0.7, y: 2.6, w: 11.9, h: 1.6,
    fontFace: FONT_HEAD, fontSize: 40, color: WHITE, bold: false,
    valign: "top",
  });

  const sub = [content.organisation, content.edition_year].filter(Boolean).join(" · ");
  if (sub) {
    slide.addText(sub, {
      x: 0.7, y: 4.15, w: 11.9, h: 0.5,
      fontFace: FONT_BODY, fontSize: 16, color: "B9C4D1",
    });
  }

  slide.addText("Executive Brief", {
    x: 0.7, y: 6.6, w: 8, h: 0.4,
    fontFace: FONT_BODY, fontSize: 12, color: "7A879A",
  });
}

// ---------------------------------------------------------------
// Slide 2 — UAE Headline (big-number treatment, not a bullet slide)
// ---------------------------------------------------------------
{
  const slide = pres.addSlide();
  slide.background = { color: WHITE };

  slide.addText("UAE PERFORMANCE", {
    x: 0.7, y: 0.5, w: 8, h: 0.4,
    fontFace: FONT_BODY, fontSize: 11, color: GOLD, bold: true, charSpacing: 2,
  });

  // Large card with the headline stat
  slide.addShape(pres.ShapeType.roundRect, {
    x: 0.7, y: 1.2, w: 11.9, h: 3.0,
    rectRadius: 0.08,
    fill: { color: CREAM },
    line: { type: "none" },
  });

  slide.addText(content.uae_headline || "Not stated on source page", {
    x: 1.1, y: 1.6, w: 11.1, h: 2.2,
    fontFace: FONT_HEAD, fontSize: 28, color: NAVY,
    valign: "middle",
  });

  if (content.key_findings && content.key_findings.length) {
    slide.addText("KEY FINDINGS", {
      x: 0.7, y: 4.5, w: 8, h: 0.35,
      fontFace: FONT_BODY, fontSize: 11, color: SLATE, bold: true, charSpacing: 1.5,
    });

    const bulletItems = content.key_findings.map((finding, i) => ({
      text: finding,
      options: {
        bullet: { code: "2022" },
        color: INK,
        fontSize: 14,
        fontFace: FONT_BODY,
        breakLine: i < content.key_findings.length - 1,
        paraSpaceAfter: 10,
      },
    }));
    slide.addText(bulletItems, { x: 0.9, y: 4.9, w: 11.5, h: 2.2 });
  }
}

// ---------------------------------------------------------------
// Slide 3 — Benchmark Comparison (G7 / G20 / BRICS groups, only if data exists)
// ---------------------------------------------------------------
if (content.benchmark_groups && content.benchmark_groups.length > 0) {
  const slide = pres.addSlide();
  slide.background = { color: WHITE };

  slide.addText("BENCHMARK COMPARISON", {
    x: 0.7, y: 0.5, w: 8, h: 0.4,
    fontFace: FONT_BODY, fontSize: 11, color: GOLD, bold: true, charSpacing: 2,
  });

  slide.addText("UAE vs. Standard Peer Groups", {
    x: 0.7, y: 0.95, w: 11.5, h: 0.6,
    fontFace: FONT_HEAD, fontSize: 24, color: NAVY,
  });

  // Lay out up to 3 group cards side by side
  const groups = content.benchmark_groups.slice(0, 3);
  const cardW = 3.9;
  const gap = 0.25;
  const startX = 0.7;
  const cardY = 1.85;
  const cardH = 4.9;

  groups.forEach((group, i) => {
    const x = startX + i * (cardW + gap);

    slide.addShape(pres.ShapeType.roundRect, {
      x, y: cardY, w: cardW, h: cardH,
      rectRadius: 0.06,
      fill: { color: CREAM },
      line: { type: "none" },
    });

    slide.addText(group.group || "", {
      x: x + 0.25, y: cardY + 0.2, w: cardW - 0.5, h: 0.4,
      fontFace: FONT_HEAD, fontSize: 18, color: NAVY, bold: true,
    });

    // Average, if computed
    let yCursor = cardY + 0.75;
    if (group.average) {
      slide.addText(group.average, {
        x: x + 0.25, y: yCursor, w: cardW - 0.5, h: 0.55,
        fontFace: FONT_HEAD, fontSize: 26, color: GOLD, bold: true,
      });
      yCursor += 0.65;
    }

    if (group.coverage_note) {
      slide.addText(group.coverage_note, {
        x: x + 0.25, y: yCursor, w: cardW - 0.5, h: 0.55,
        fontFace: FONT_BODY, fontSize: 10, italic: true, color: SLATE,
      });
      yCursor += 0.6;
    }

    // Individual member figures found
    if (group.members_found && group.members_found.length) {
      const memberLines = group.members_found.map((m, mi) => ({
        text: `${m.country}: ${m.value}`,
        options: {
          color: INK,
          fontSize: 12,
          fontFace: FONT_BODY,
          bold: (m.country || "").toUpperCase().includes("UAE") ||
                (m.country || "").toUpperCase().includes("UNITED ARAB EMIRATES"),
          breakLine: mi < group.members_found.length - 1,
          paraSpaceAfter: 6,
        },
      }));
      slide.addText(memberLines, {
        x: x + 0.25, y: yCursor, w: cardW - 0.5, h: cardH - (yCursor - cardY) - 0.2,
        valign: "top",
      });
    }
  });
}

// ---------------------------------------------------------------
// Slide 4 — Methodology & Summary
// ---------------------------------------------------------------
{
  const slide = pres.addSlide();
  slide.background = { color: WHITE };

  slide.addText("METHODOLOGY & SUMMARY", {
    x: 0.7, y: 0.5, w: 8, h: 0.4,
    fontFace: FONT_BODY, fontSize: 11, color: GOLD, bold: true, charSpacing: 2,
  });

  slide.addText("How the Ranking Works", {
    x: 0.7, y: 0.95, w: 11.5, h: 0.5,
    fontFace: FONT_HEAD, fontSize: 20, color: NAVY,
  });

  slide.addText(content.methodology_summary || "Methodology not detailed on the source page.", {
    x: 0.7, y: 1.55, w: 11.5, h: 1.3,
    fontFace: FONT_BODY, fontSize: 14, color: INK, valign: "top",
  });

  // Divider for visual rhythm instead of empty gap
  slide.addShape(pres.ShapeType.rect, {
    x: 0.7, y: 3.15, w: 11.5, h: 0.012,
    fill: { color: "DCD5C4" },
    line: { type: "none" },
  });

  slide.addText("Summary", {
    x: 0.7, y: 3.45, w: 11.5, h: 0.5,
    fontFace: FONT_HEAD, fontSize: 20, color: NAVY,
  });

  slide.addText(content.summary || "", {
    x: 0.7, y: 4.05, w: 11.5, h: 2.7,
    fontFace: FONT_BODY, fontSize: 15, color: INK, valign: "top",
    lineSpacingMultiple: 1.25,
  });

  slide.addText("Prepared automatically from the report's official source page. Verify figures against the original before external use.", {
    x: 0.7, y: 6.95, w: 11.9, h: 0.35,
    fontFace: FONT_BODY, fontSize: 9, color: SLATE, italic: true,
  });
}

pres.writeFile({ fileName: outputPath }).then(() => {
  console.log(`Wrote ${outputPath}`);
});
