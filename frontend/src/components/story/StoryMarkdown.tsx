"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

/**
 * Aggressively fix stray/broken LaTeX in LLM output before KaTeX processes it.
 *
 * Common failure modes:
 * 1. \text{foo} outside $...$ → wrap in math
 * 2. Python eats \t → "text{foo}" (bare, no backslash) → restore and wrap
 * 3. \times outside math → rendered as literal text
 * 4. Bare "times10^{-50}" (backslash eaten) → restore
 * 5. Mismatched/nested $ delimiters → fix pairs
 * 6. \sim, \approx, \chi, \Delta outside math
 */
function sanitizeLatex(text: string): string {
  // Step 1: Fix broken $ delimiter pairs. KaTeX chokes on odd $ counts.
  // Remove $ that are clearly broken (e.g., "$_\text{lag}$_rows" → wrap whole thing)
  // Strategy: split on $$...$$ first (display math), then $...$ (inline math)

  // Step 2: Process non-math segments
  const parts = text.split(/(\$\$[\s\S]*?\$\$|\$(?:[^$\n]|\\\$)+?\$)/g);
  return parts
    .map((part) => {
      // Already a math block — leave alone
      if (
        (part.startsWith("$$") && part.endsWith("$$")) ||
        (part.startsWith("$") && part.endsWith("$") && part.length > 2)
      ) {
        return part;
      }

      let f = part;

      // --- Restore bare commands where Python ate the backslash ---

      // "text{foo}" → "$\text{foo}$" (Python \t → tab ate the backslash)
      f = f.replace(
        /(?<![\\a-zA-Z])text\{([^}]*)\}/g,
        (_m, inner) => `$\\text{${inner}}$`,
      );
      // "textit{foo}" → "$\textit{foo}$"
      f = f.replace(
        /(?<![\\a-zA-Z])textit\{([^}]*)\}/g,
        (_m, inner) => `$\\textit{${inner}}$`,
      );
      // "textbf{foo}" → "$\textbf{foo}$"
      f = f.replace(
        /(?<![\\a-zA-Z])textbf\{([^}]*)\}/g,
        (_m, inner) => `$\\textbf{${inner}}$`,
      );
      // "mathrm{foo}" → "$\mathrm{foo}$"
      f = f.replace(
        /(?<![\\a-zA-Z])mathrm\{([^}]*)\}/g,
        (_m, inner) => `$\\mathrm{${inner}}$`,
      );
      // "mathit{foo}" → "$\mathit{foo}$"
      f = f.replace(
        /(?<![\\a-zA-Z])mathit\{([^}]*)\}/g,
        (_m, inner) => `$\\mathit{${inner}}$`,
      );

      // --- Properly escaped \command{...} outside $...$ ---
      f = f.replace(
        /\\(text|textit|textbf|textrm|texttt|mathrm|mathit|mathbf|bar|hat|tilde|vec|overline|underline|sqrt|frac)\{/g,
        (_m, cmd) => `$\\${cmd}{`,
      );
      // Close the opened math block after the closing }
      // This is tricky — find matching } and add $
      // Simpler: just wrap \cmd{...} as a unit
      f = f.replace(
        /\$\\(text|textit|textbf|textrm|texttt|mathrm|mathit|mathbf|bar|hat|tilde|vec|overline|underline|sqrt)\{([^}]*)\}(?!\$)/g,
        (_m, cmd, inner) => `$\\${cmd}{${inner}}$`,
      );

      // --- Bare "times10^{-N}" or "times 10^{-N}" (backslash eaten) ---
      f = f.replace(
        /(?<![\\a-zA-Z])times\s*(\d+)\^?\{([^}]*)\}/g,
        (_m, base, exp) => `$\\times ${base}^{${exp}}$`,
      );
      f = f.replace(
        /(?<![\\a-zA-Z])times\s*(\d+)\^(-?\d+)/g,
        (_m, base, exp) => `$\\times ${base}^{${exp}}$`,
      );

      // --- Bare "sim" before numbers (Python \s → space ate backslash for \sim) ---
      f = f.replace(
        /(?<![\\a-zA-Z])sim(\d)/g,
        (_m, d) => `$\\sim$${d}`,
      );
      f = f.replace(
        /(?<![\\a-zA-Z])simC\(/g,
        () => `$\\sim$ C(`,
      );

      // --- Bare "approx" before numbers ---
      f = f.replace(
        /(?<![\\a-zA-Z])approx(\d)/g,
        (_m, d) => `$\\approx$${d}`,
      );

      // --- Standalone \commands outside math ---
      f = f.replace(
        /\\(times|approx|geq|leq|pm|Delta|delta|chi|rho|sigma|mu|alpha|beta|gamma|lambda|infty|neq|sim|propto|cdot|ldots|ge|le|ll|gg|equiv)(?![a-zA-Z{])/g,
        (_m, cmd) => `$\\${cmd}$`,
      );

      // --- N^{exp} outside math (common: 10^{-50}) ---
      f = f.replace(
        /(\d+)\^?\{(-?[\d.]+)\}/g,
        (_m, base, exp) => `$${base}^{${exp}}$`,
      );
      // N^exp (no braces, like 10^4)
      f = f.replace(
        /(\d+)\^(-?\d+)(?![\d}])/g,
        (_m, base, exp) => `$${base}^{${exp}}$`,
      );

      // --- Subscripts outside math: word_{sub} ---
      f = f.replace(
        /([a-zA-Z])\\_?\{([^}]*)\}/g,
        (_m, pre, sub) => `${pre}$_{${sub}}$`,
      );

      // --- "textLevene" style (bare \text that got mangled into one word) ---
      // Catch: textFoo where Foo starts with uppercase → $\text{Foo}$
      f = f.replace(
        /(?<![a-zA-Z])text([A-Z][a-zA-Z_]*)/g,
        (_m, word) => `$\\text{${word}}$`,
      );

      // --- Fix leftover bare \frac{}{} ---
      f = f.replace(
        /\\frac\{([^}]*)\}\{([^}]*)\}/g,
        (_m, num, den) => `$\\frac{${num}}{${den}}$`,
      );

      // --- Clean up double-wrapped math: $$...$$ from our fixes ---
      f = f.replace(/\$\$([^$]+)\$\$/g, (m, inner) => {
        // Only unwrap if this looks like inline math we accidentally double-wrapped
        if (!inner.includes("\n")) return `$${inner}$`;
        return m;
      });

      // --- Clean up empty math blocks ---
      f = f.replace(/\$\s*\$/g, "");

      return f;
    })
    .join("");
}

interface StoryMarkdownProps {
  content: string;
  className?: string;
}

export default function StoryMarkdown({ content, className }: StoryMarkdownProps) {
  const sanitized = sanitizeLatex(content);
  return (
    <div className={`report-prose prose prose-sm max-w-none text-on-surface-variant ${className || ""}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {sanitized}
      </ReactMarkdown>
    </div>
  );
}

// Export for reuse in chat messages
export { sanitizeLatex };
