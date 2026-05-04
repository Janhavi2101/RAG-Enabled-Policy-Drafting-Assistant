import React from "react";
import { Document, Page, StyleSheet, Text, View, pdf } from "@react-pdf/renderer";

const styles = StyleSheet.create({
  page: {
    paddingTop: 78,
    paddingBottom: 62,
    paddingHorizontal: 62,
    fontSize: 10.2,
    lineHeight: 1.48,
    color: "#111827",
    fontFamily: "Times-Roman",
    backgroundColor: "#FFFFFF",
  },
  header: {
    position: "absolute",
    top: 26,
    left: 62,
    right: 62,
    paddingBottom: 6,
    borderBottomWidth: 0.7,
    borderBottomColor: "#BFC7D1",
    alignItems: "center",
  },
  headerTitle: {
    fontSize: 9.2,
    textTransform: "uppercase",
    color: "#374151",
    letterSpacing: 0.8,
    fontFamily: "Times-Bold",
    textAlign: "center",
  },
  footer: {
    position: "absolute",
    bottom: 22,
    left: 62,
    right: 62,
    paddingTop: 6,
    borderTopWidth: 0.7,
    borderTopColor: "#D6DCE5",
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  footerText: {
    fontSize: 8.8,
    color: "#4B5563",
    fontFamily: "Times-Italic",
  },
  titleBlock: {
    marginBottom: 16,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#C7CDD4",
    alignItems: "center",
  },
  titleEyebrow: {
    fontSize: 8.8,
    textTransform: "uppercase",
    color: "#4B5563",
    letterSpacing: 0.9,
    marginBottom: 8,
    fontFamily: "Times-Bold",
  },
  title: {
    fontSize: 18.4,
    lineHeight: 1.2,
    fontFamily: "Times-Bold",
    color: "#111827",
    marginBottom: 6,
    textAlign: "center",
    textTransform: "uppercase",
  },
  generatedText: {
    fontSize: 9.2,
    color: "#4B5563",
    fontFamily: "Times-Italic",
    textAlign: "center",
  },
  metaPanel: {
    marginBottom: 14,
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderWidth: 0.8,
    borderColor: "#C7CDD4",
    backgroundColor: "#FFFFFF",
  },
  metaGrid: {
    flexDirection: "row",
    gap: 8,
  },
  metaItem: {
    flex: 1,
  },
  metaLabel: {
    fontSize: 8.2,
    textTransform: "uppercase",
    color: "#4B5563",
    letterSpacing: 0.5,
    marginBottom: 2,
    fontFamily: "Times-Bold",
  },
  metaValue: {
    fontSize: 10.1,
    color: "#111827",
    fontFamily: "Times-Roman",
  },
  body: {
    paddingBottom: 8,
  },
  sectionBlock: {
    marginTop: 10,
    marginBottom: 6,
    paddingTop: 3,
  },
  sectionHeading: {
    fontSize: 12.3,
    fontFamily: "Times-Bold",
    color: "#111827",
    lineHeight: 1.3,
    textTransform: "uppercase",
  },
  sectionHeadingMuted: {
    color: "#1F2937",
  },
  paragraph: {
    marginBottom: 5,
    textAlign: "justify",
    color: "#1F2937",
  },
  introParagraph: {
    marginBottom: 6,
    textAlign: "justify",
    color: "#1F2937",
    fontSize: 10.4,
  },
  listRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: 3,
    paddingRight: 4,
  },
  listRowEmphasis: {
    marginBottom: 4,
  },
  bullet: {
    width: 13,
    color: "#111827",
    fontFamily: "Times-Roman",
  },
  bulletText: {
    flex: 1,
    textAlign: "justify",
    color: "#1F2937",
  },
  numberLabel: {
    width: 20,
    color: "#111827",
    fontFamily: "Times-Bold",
  },
  compactList: {
    marginTop: 2,
    marginBottom: 2,
  },
  referenceText: {
    fontSize: 9.7,
  },
  documentCode: {
    marginTop: 4,
    fontSize: 8.7,
    color: "#4B5563",
    fontFamily: "Times-Italic",
    textAlign: "center",
  },
});

const EMPHASIZED_HEADINGS = new Set(["Compliance Review", "Legal Notes", "References"]);

function normalizeHeadingText(value) {
  return value
    .replace(/^\d+\.\s*/, "")
    .replace(/:$/, "")
    .trim()
    .toLowerCase();
}

function parseMetaLine(text) {
  if (!text.includes("|")) return null;

  const parts = text
    .split("|")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const [label, ...rest] = part.split(":");
      if (!rest.length) return null;
      return {
        label: label.trim(),
        value: rest.join(":").trim(),
      };
    })
    .filter(Boolean);

  return parts.length ? parts : null;
}

function classifyHeading(text) {
  const cleanText = text.replace(/^\d+\.\s*/, "").trim();
  return EMPHASIZED_HEADINGS.has(cleanText);
}

function parseMarkdownToBlocks(markdown) {
  const lines = markdown.split(/\r?\n/);
  const blocks = [];
  let paragraphBuffer = [];
  let bulletBuffer = [];
  let numberedBuffer = [];
  let previousHeadingText = "";
  let currentHeadingText = "";

  const flushParagraph = () => {
    if (!paragraphBuffer.length) return;

    const paragraphText = paragraphBuffer.join(" ").trim();
    if (!paragraphText) {
      paragraphBuffer = [];
      return;
    }

    if (normalizeHeadingText(paragraphText) === normalizeHeadingText(previousHeadingText)) {
      paragraphBuffer = [];
      return;
    }

    const parsedMeta = parseMetaLine(paragraphText);
    if (parsedMeta) {
      blocks.push({
        type: "meta",
        items: parsedMeta,
      });
    } else {
      blocks.push({
        type: "paragraph",
        text: paragraphText,
      });
    }

    paragraphBuffer = [];
  };

  const flushBullets = () => {
    if (!bulletBuffer.length) return;
    bulletBuffer.forEach((item) => {
      blocks.push({ type: "bullet", text: item });
    });
    bulletBuffer = [];
  };

  const flushNumbered = () => {
    if (!numberedBuffer.length) return;
    numberedBuffer.forEach((item) => {
      blocks.push({ type: "numbered", number: item.number, text: item.text });
    });
    numberedBuffer = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line) {
      flushParagraph();
      flushBullets();
      flushNumbered();
      continue;
    }

    if (line.startsWith("# ")) {
      flushParagraph();
      flushBullets();
      flushNumbered();
      previousHeadingText = line.slice(2).trim();
      currentHeadingText = previousHeadingText;
      blocks.push({ type: "heading1", text: previousHeadingText });
      continue;
    }

    if (line.startsWith("## ")) {
      flushParagraph();
      flushBullets();
      flushNumbered();
      previousHeadingText = line.slice(3).trim();
      currentHeadingText = previousHeadingText;
      blocks.push({
        type: "heading2",
        text: previousHeadingText,
        emphasized: classifyHeading(previousHeadingText),
      });
      continue;
    }

    if (/references$/i.test(currentHeadingText) && /^\[\d+\]\s+/.test(line)) {
      flushParagraph();
      flushBullets();
      flushNumbered();
      bulletBuffer.push(line);
      continue;
    }

    if (line.startsWith("- ")) {
      flushParagraph();
      flushNumbered();
      bulletBuffer.push(line.slice(2).trim());
      continue;
    }

    const numberedMatch = line.match(/^(\d+)\.\s+(.*)$/);
    if (numberedMatch) {
      flushParagraph();
      flushBullets();
      numberedBuffer.push({
        number: `${numberedMatch[1]}.`,
        text: numberedMatch[2].trim(),
      });
      continue;
    }

    paragraphBuffer.push(line);
  }

  flushParagraph();
  flushBullets();
  flushNumbered();

  return blocks;
}

function extractDocumentTitle(blocks) {
  const titleBlock = blocks.find((block) => block.type === "heading1");
  return titleBlock?.text || "Policy Draft";
}

function sanitizeFileName(title) {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "") || "policy_draft";
}

function PolicyPdfDocument({ blocks, title }) {
  const generatedAt = new Date().toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });

  const contentBlocks = blocks.filter((block) => block.type !== "heading1");
  const firstMetaBlockIndex = contentBlocks.findIndex((block) => block.type === "meta");

  return (
    <Document>
      <Page size="A4" style={styles.page}>
        <View style={styles.header} fixed>
          <Text style={styles.headerTitle}>{title}</Text>
        </View>

        <View style={styles.titleBlock}>
          <Text style={styles.titleEyebrow}>Hospital Policy Document</Text>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.generatedText}>Prepared on {generatedAt}</Text>
          <Text style={styles.documentCode}>For internal policy use and administrative circulation</Text>
        </View>

        <View style={styles.body}>
          {contentBlocks.map((block, index) => {
            const previousBlock = index > 0 ? contentBlocks[index - 1] : null;

            if (block.type === "meta") {
              return (
                <View key={`block-${index}`} style={styles.metaPanel}>
                  <View style={styles.metaGrid}>
                    {block.items.map((item, itemIndex) => (
                      <View key={`meta-${itemIndex}`} style={styles.metaItem}>
                        <Text style={styles.metaLabel}>{item.label}</Text>
                        <Text style={styles.metaValue}>{item.value}</Text>
                      </View>
                    ))}
                  </View>
                </View>
              );
            }

            if (block.type === "heading2") {
              return (
                <View key={`block-${index}`} style={styles.sectionBlock} wrap={false}>
                  <Text
                    style={[
                      styles.sectionHeading,
                      block.emphasized ? styles.sectionHeadingMuted : null,
                    ]}
                  >
                    {block.text}
                  </Text>
                </View>
              );
            }

            if (block.type === "bullet") {
              const isReferenceItem = previousBlock?.type === "heading2" && /references$/i.test(previousBlock.text);
              return (
                <View
                  key={`block-${index}`}
                  style={[
                    styles.listRow,
                    block.text.startsWith("[") ? styles.listRowEmphasis : null,
                    isReferenceItem ? styles.listRowEmphasis : null,
                    firstMetaBlockIndex === -1 && index === 0 ? styles.compactList : null,
                  ]}
                >
                  <Text style={styles.bullet}>{isReferenceItem ? "\u2022" : "-"}</Text>
                  <Text style={[styles.bulletText, isReferenceItem ? styles.referenceText : null]}>{block.text}</Text>
                </View>
              );
            }

            if (block.type === "numbered") {
              const isReferenceItem = previousBlock?.type === "heading2" && /references$/i.test(previousBlock.text);
              return (
                <View key={`block-${index}`} style={[styles.listRow, isReferenceItem ? styles.listRowEmphasis : null]}>
                  <Text style={styles.numberLabel}>{isReferenceItem ? "\u2022" : block.number}</Text>
                  <Text style={[styles.bulletText, isReferenceItem ? styles.referenceText : null]}>{block.text}</Text>
                </View>
              );
            }

            return (
              <Text
                key={`block-${index}`}
                style={firstMetaBlockIndex === -1 && index === 0 ? styles.introParagraph : styles.paragraph}
              >
                {block.text}
              </Text>
            );
          })}
        </View>

        <View style={styles.footer} fixed>
          <Text style={styles.footerText}>Internal policy draft</Text>
          <Text
            style={styles.footerText}
            render={({ pageNumber, totalPages }) => `Page ${pageNumber} of ${totalPages}`}
          />
        </View>
      </Page>
    </Document>
  );
}

export async function buildPolicyPdf(markdown) {
  const blocks = parseMarkdownToBlocks(markdown || "");
  const title = extractDocumentTitle(blocks);
  const fileName = `${sanitizeFileName(title)}_${Date.now()}.pdf`;
  const blob = await pdf(<PolicyPdfDocument blocks={blocks} title={title} />).toBlob();
  return { blob, fileName };
}
