import { Fragment, type ReactNode } from "react";

/**
 * Tiny markdown → React renderer. Covers the subset our editor produces:
 *
 *   # / ## / ### headings
 *   paragraphs
 *   - / * unordered lists      → <ul>
 *   1. / 2. ordered lists      → <ol>
 *   ![alt](url) inline image   → <img>
 *   ```code block```           → <pre><code>
 *   inline:  **bold**, *italic*, `code`, [text](url)
 *
 * Unsupported syntax falls back to plain text. We deliberately don't pull
 * in `react-markdown` / `remark` — keeps the marketing bundle small and the
 * sanitization surface minimal. Anything fancier (tables, footnotes) can
 * land alongside a richer editor later.
 */
export function renderMarkdown(source: string): ReactNode {
  const lines = (source || "").replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block.
    if (line.startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        buf.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++; // consume closing fence
      blocks.push(
        <pre
          key={key++}
          className="my-4 overflow-x-auto rounded-xl bg-ink px-4 py-3 text-xs text-grape-50"
        >
          <code>{buf.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    // Headings.
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const content = heading[2];
      const cls = HEADING_CLASS[level];
      const Tag: "h2" | "h3" | "h4" =
        level === 1 ? "h2" : level === 2 ? "h3" : "h4";
      blocks.push(
        <Tag key={key++} className={cls}>
          {renderInline(content)}
        </Tag>,
      );
      i++;
      continue;
    }

    // Image-only line (we treat ![alt](url) as a block when on its own).
    const imgMatch = /^!\[([^\]]*)\]\(([^)\s]+)\)\s*$/.exec(line);
    if (imgMatch) {
      blocks.push(
        <figure key={key++} className="my-6">
          <img
            src={imgMatch[2]}
            alt={imgMatch[1]}
            className="rounded-2xl border border-slate-100"
            loading="lazy"
          />
          {imgMatch[1] ? (
            <figcaption className="mt-2 text-xs text-slate-500">
              {imgMatch[1]}
            </figcaption>
          ) : null}
        </figure>,
      );
      i++;
      continue;
    }

    // Unordered list.
    if (/^[\-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[\-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[\-*]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul
          key={key++}
          className="my-4 ml-5 list-disc text-base text-slate-700"
        >
          {items.map((it, idx) => (
            <li key={idx} className="mt-1">
              {renderInline(it)}
            </li>
          ))}
        </ul>,
      );
      continue;
    }

    // Ordered list.
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s+/, ""));
        i++;
      }
      blocks.push(
        <ol
          key={key++}
          className="my-4 ml-5 list-decimal text-base text-slate-700"
        >
          {items.map((it, idx) => (
            <li key={idx} className="mt-1">
              {renderInline(it)}
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    // Blank line — skip.
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Paragraph (collect consecutive non-blank, non-special lines).
    const buf: string[] = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^(#{1,3}\s|[\-*]\s|\d+\.\s|```|!\[)/.test(lines[i])
    ) {
      buf.push(lines[i]);
      i++;
    }
    blocks.push(
      <p key={key++} className="my-4 text-base leading-relaxed text-slate-700">
        {renderInline(buf.join(" "))}
      </p>,
    );
  }

  return <Fragment>{blocks}</Fragment>;
}


const HEADING_CLASS: Record<number, string> = {
  1: "mt-8 text-3xl font-semibold tracking-tight text-ink",
  2: "mt-8 text-2xl font-semibold tracking-tight text-ink",
  3: "mt-6 text-xl font-semibold text-ink",
};


/**
 * Inline runs: links, bold, italic, code, inline images. Returns a single
 * fragment of mixed nodes. We don't try to be fully spec-compliant — the
 * editor produces a narrow subset and pasted bodies fall back to plain text
 * when our regexes don't match.
 */
function renderInline(text: string): ReactNode {
  // Tokenize by scanning for the next markdown construct each pass.
  const out: ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  const re =
    /(\*\*([^*]+)\*\*)|(\*([^*]+)\*)|(`([^`]+)`)|(\[([^\]]+)\]\(([^)\s]+)\))|(!\[([^\]]*)\]\(([^)\s]+)\))/g;

  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > cursor) {
      out.push(text.slice(cursor, m.index));
    }
    if (m[1]) {
      out.push(
        <strong key={key++} className="font-semibold text-ink">
          {m[2]}
        </strong>,
      );
    } else if (m[3]) {
      out.push(<em key={key++}>{m[4]}</em>);
    } else if (m[5]) {
      out.push(
        <code
          key={key++}
          className="rounded bg-grape-100 px-1 py-0.5 font-mono text-xs text-grape-700"
        >
          {m[6]}
        </code>,
      );
    } else if (m[7]) {
      out.push(
        <a
          key={key++}
          href={m[9]}
          className="text-grape-700 underline-offset-2 hover:underline"
          target={m[9].startsWith("http") ? "_blank" : undefined}
          rel={m[9].startsWith("http") ? "noopener noreferrer" : undefined}
        >
          {m[8]}
        </a>,
      );
    } else if (m[10]) {
      out.push(
        <img
          key={key++}
          src={m[12]}
          alt={m[11]}
          className="my-2 inline-block max-h-40 rounded-lg border border-slate-100"
          loading="lazy"
        />,
      );
    }
    cursor = m.index + m[0].length;
  }
  if (cursor < text.length) {
    out.push(text.slice(cursor));
  }
  return <>{out}</>;
}
