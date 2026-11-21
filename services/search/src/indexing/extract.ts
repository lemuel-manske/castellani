import { parse, type HTMLElement } from "node-html-parser";
import { WARCParser } from "warcio";

import { type ExtractedPage, DocumentError, UnsupportedContentError } from "./model.js";

const HTML_TYPES = new Set(["text/html", "application/xhtml+xml"]);
const NON_CONTENT_SELECTOR = "script, style, noscript, template, svg, iframe, object";
const BLOCK_SELECTOR =
  "address, article, aside, blockquote, br, dd, div, dl, dt, figcaption, figure, footer, form, " +
  "h1, h2, h3, h4, h5, h6, header, hr, li, main, nav, ol, p, pre, section, table, td, th, tr, ul";

/** Upper bound for indexed text per snapshot; longer pages are truncated. */
export const MAX_CONTENT_CHARS = 500_000;

/**
 * Finds the HTTP response record for the captured page in a set of WARC files
 * and extracts its searchable text. `targets` are the page URLs in order of
 * preference (final URL after redirects first).
 */
export async function extractPage(warcs: Iterable<Uint8Array>, targets: string[]): Promise<ExtractedPage> {
  const wanted = targets.map(normalizeUrl).filter((url): url is string => url !== undefined);

  if (wanted.length === 0) {
    throw new DocumentError("page has no valid target URL");
  }

  const responses = new Map<string, { html: string; contentType: string }>();

  for (const warc of warcs) {
    try {
      for await (const record of new WARCParser([warc])) {
        if (record.warcType !== "response") {
          continue;
        }

        const target = normalizeUrl(record.warcTargetURI ?? "");

        if (target === undefined || !wanted.includes(target) || responses.has(target)) {
          continue;
        }

        const status = Number(record.httpHeaders?.statusCode ?? 0);
        const contentType = mediaType(record.httpHeaders?.headers.get("content-type") ?? "");

        if (status < 200 || status > 299 || !HTML_TYPES.has(contentType)) {
          continue;
        }

        responses.set(target, { html: await record.contentText(), contentType });
      }
    } catch (error) {
      throw new DocumentError(`unreadable WARC artifact: ${describe(error)}`);
    }
  }

  const match = wanted.map((url) => responses.get(url)).find((response) => response !== undefined);

  if (match === undefined) {
    throw new UnsupportedContentError("no successful HTML response record for the captured page");
  }

  return { ...extractHtml(match.html), contentType: match.contentType };
}

/** Extracts the title and visible text from an HTML document. */
export function extractHtml(html: string): { title?: string; content: string } {
  const root = parse(html, { comment: false, blockTextElements: { pre: true } });

  const title = collapse(root.querySelector("title")?.text ?? "");

  for (const element of root.querySelectorAll(NON_CONTENT_SELECTOR)) {
    element.remove();
  }

  const body: HTMLElement = root.querySelector("body") ?? root;

  // Separate block-level elements so adjacent paragraphs do not merge words.
  for (const element of body.querySelectorAll(BLOCK_SELECTOR)) {
    element.insertAdjacentHTML("beforebegin", " ");
    element.insertAdjacentHTML("afterend", " ");
  }

  const content = collapse(body.text).slice(0, MAX_CONTENT_CHARS);

  return title ? { title, content } : { content };
}

function normalizeUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    url.hash = "";

    return url.href;
  } catch {
    return undefined;
  }
}

function mediaType(header: string): string {
  return (header.split(";", 1)[0] ?? "").trim().toLowerCase();
}

function collapse(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
