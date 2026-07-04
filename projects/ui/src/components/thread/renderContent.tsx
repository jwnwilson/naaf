import type { ReactNode } from "react";

// Violet mono styling for highlighted runs (matches D3 @mention / inline path).
const HIGHLIGHT = "font-mono text-[#bab7f6]";

/**
 * Render message text with two safe, data-backed highlights:
 *  - `@mention` tokens whose handle is in `mentions` (the parsed recipients)
 *  - inline `` `code` `` spans (backtick-delimited paths/identifiers)
 *
 * Everything else is left as plain text — we deliberately avoid heuristic path
 * detection to prevent false highlights.
 */
export function renderContent(content: string, mentions: string[] = []): ReactNode[] {
  const mentionSet = new Set(mentions);
  // Split on backtick code spans first, keeping the delimiters' inner text.
  const parts = content.split(/(`[^`]+`)/g);
  const nodes: ReactNode[] = [];

  parts.forEach((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
      nodes.push(
        <span key={`c${i}`} className={HIGHLIGHT}>
          {part.slice(1, -1)}
        </span>,
      );
      return;
    }
    // Within a plain run, highlight @mentions that are known recipients.
    const tokens = part.split(/(@[\w-]+)/g);
    tokens.forEach((tok, j) => {
      if (tok.startsWith("@") && mentionSet.has(tok.slice(1))) {
        nodes.push(
          <span key={`m${i}-${j}`} className={HIGHLIGHT}>
            {tok}
          </span>,
        );
      } else if (tok) {
        nodes.push(tok);
      }
    });
  });

  return nodes;
}
