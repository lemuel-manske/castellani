import { parse } from "node-html-parser";

interface CapturedPage {
  archiveId: string;
  snapshotId: string;
  url: string;
  finalUrl?: string;
  capturedAt: string;
  contentType?: string;
  content: string;
}

interface SearchDocument {
  archiveId: string;
  snapshotId: string;
  url: string;
  finalUrl: string;
  capturedAt: string;
  contentType: string;
  title: string;
  description: string;
  language: string;
  text: string;
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
const HTML_CONTENT_TYPES = new Set(["text/html", "application/xhtml+xml"]);
const TEXT_CONTENT_TYPES = new Set(["text/plain"]);
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
  return value.replace(/\u00a0/g, " ").replace(/[\t\r\n ]+/g, " ").trim();
}

function contentTypeOf(value: string | undefined): string {
  const mediaType = (value ?? "application/octet-stream").split(";", 1)[0];

  return (mediaType ?? "application/octet-stream").trim().toLowerCase();
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
    text: normalizeText((root.querySelector("body") ?? root).textContent),
  };
}

function extractSearchableContent(
  page: CapturedPage,
  options: ExtractionOptions = {},
): ContentExtraction {
  const contentType = contentTypeOf(page.contentType);
  const maxTextLength = options.maxTextLength ?? DEFAULT_MAX_TEXT_LENGTH;

  if (
    !HTML_CONTENT_TYPES.has(contentType) &&
    !TEXT_CONTENT_TYPES.has(contentType)
  ) {
    return { kind: "UNSUPPORTED", reasonCode: "UNSUPPORTED_CONTENT_TYPE" };
  }

  const extracted = HTML_CONTENT_TYPES.has(contentType)
    ? extractHtml(page.content)
    : {
        title: "",
        description: "",
        language: "",
        text: normalizeText(page.content),
      };
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
      contentType,
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
  SearchDocument
};
