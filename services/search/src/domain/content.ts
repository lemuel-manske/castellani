import { parse } from "node-html-parser";

interface CapturedPage {
  archiveId: string;
  snapshotId: string;

  url: string;

  finalUrl?: string;

  capturedAt: string;

  content: string;
}

interface SearchDocument {
  archiveId: string;
  snapshotId: string;

  url: string;

  finalUrl: string;

  capturedAt: string;

  title: string;
  description: string;
  text: string;

  language: string;
}

type ContentExtraction =
  | { kind: "INDEXABLE"; document: SearchDocument }
  | {
      kind: "UNSUPPORTED";
      reasonCode: "UNSUPPORTED_CONTENT_TYPE" | "EMPTY_CONTENT";
    };

interface ExtractionOptions {
  maxTextLength?: number;
}

const DEFAULT_MAX_TEXT_LENGTH = 1_000_000;

const NON_CONTENT_ELEMENTS = [
  "script",
  "style",
  "noscript",
  "template",
  "svg",
  "canvas",
  "iframe",
  "object",
  "embed",
  "nav",
  "header",
  "footer",
  "aside",
  "form",
  "button",
  "input",
  "select",
  "textarea",
];

function normalizeText(value: string): string {
  return value
    .replace(/\u00a0/g, " ")
    .replace(/[\t\r\n ]+/g, " ")
    .trim();
}

function metaContent(root: ReturnType<typeof parse>, name: string): string {
  const element = root.querySelectorAll("meta").find((candidate) => {
    const key =
      candidate.getAttribute("name") ?? candidate.getAttribute("property");

    return key?.toLowerCase() === name;
  });

  return normalizeText(element?.getAttribute("content") ?? "");
}

function extractHtml(content: string): {
  title: string;
  description: string;
  language: string;
  text: string;
} {
  const root = parse(content);

  const title = normalizeText(root.querySelector("title")?.textContent ?? "");

  const description =
    metaContent(root, "description") || metaContent(root, "og:description");

  const language = normalizeText(
    root.querySelector("html")?.getAttribute("lang") ?? "",
  );

  for (const selector of NON_CONTENT_ELEMENTS) {
    for (const element of root.querySelectorAll(selector)) {
      element.remove();
    }
  }

  for (const element of root.querySelectorAll(
    "[hidden], [aria-hidden='true']",
  )) {
    element.remove();
  }

  return {
    title,
    description,
    language,
    text: normalizeText((root.querySelector("body") ?? root).structuredText),
  };
}

function extractSearchableContent(
  page: CapturedPage,
  options: ExtractionOptions = {},
): ContentExtraction {
  const maxTextLength = options.maxTextLength ?? DEFAULT_MAX_TEXT_LENGTH;

  const extracted = extractHtml(page.content)

  const text = extracted.text.slice(0, maxTextLength);

  if (!text) {
    return { kind: "UNSUPPORTED", reasonCode: "EMPTY_CONTENT" };
  }

  return {
    kind: "INDEXABLE",
    document: {
      archiveId: page.archiveId,
      snapshotId: page.snapshotId,
      url: page.url,
      finalUrl: page.finalUrl ?? page.url,
      capturedAt: page.capturedAt,
      title: extracted.title,
      description: extracted.description,
      language: extracted.language,
      text,
    },
  };
}

export { extractSearchableContent };
export type {
  CapturedPage,
  ContentExtraction,
  ExtractionOptions,
  SearchDocument,
};
