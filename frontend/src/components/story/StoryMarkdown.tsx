"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

/**
 * Fix stray LaTeX that the LLM outputs without $...$ delimiters.
 * Wraps common LaTeX commands in inline math so KaTeX can render them.
 */
function sanitizeLatex(text: string): string {
  // Don't touch content already inside $...$ blocks
  const parts = text.split(/(\$\$[\s\S]*?\$\$|\$[^$\n]+?\$)/g);
  return parts
    .map((part) => {
      // Already a math block — leave alone
      if (
        (part.startsWith("$$") && part.endsWith("$$")) ||
        (part.startsWith("$") && part.endsWith("$") && part.length > 1)
      ) {
        return part;
      }
      // Wrap stray \command{...} patterns in $...$
      // Matches: \text{...}, \textit{...}, \bar{...}, \hat{...}, \Delta, \chi, \rho etc.
      let fixed = part;
      // Multi-char commands with braces: \text{foo}, \textit{bar}, \mathrm{x}
      fixed = fixed.replace(
        /\\(text|textit|textbf|textrm|texttt|mathrm|mathit|mathbf|bar|hat|tilde|vec|overline|underline|sqrt)\{([^}]*)\}/g,
        (_m, cmd, inner) => `$\\${cmd}{${inner}}$`,
      );
      // Standalone commands: \times, \approx, \geq, \leq, \pm, \Delta, \chi, \rho, \sigma, \mu, \alpha, \beta, \gamma, \lambda, \infty, \in
      fixed = fixed.replace(
        /\\(times|approx|geq|leq|pm|Delta|delta|chi|rho|sigma|mu|alpha|beta|gamma|lambda|infty|in|neq|sim|propto|cdot|ldots)(?![a-zA-Z{])/g,
        (_m, cmd) => `$\\${cmd}$`,
      );
      // \text{...} followed by numbers/subscripts outside math: e.g. \text{resid}_MAD
      // Pattern: sequences like textresid_var, textresid_MAD — these are mangled \text{resid}_{var}
      // Also fix n_{...} style subscripts outside math
      fixed = fixed.replace(
        /([a-zA-Z])_\{([^}]*)\}/g,
        (_m, pre, sub) => `${pre}$_{${sub}}$`,
      );
      fixed = fixed.replace(
        /([a-zA-Z])_([a-zA-Z0-9]+)/g,
        (_m, pre, sub) => `${pre}$_\\text{${sub}}$`,
      );
      // Wrap stray \frac{...}{...}
      fixed = fixed.replace(
        /\\frac\{([^}]*)\}\{([^}]*)\}/g,
        (_m, num, den) => `$\\frac{${num}}{${den}}$`,
      );
      // Fix 10^{-N} patterns outside math
      fixed = fixed.replace(
        /(\d+)\^?\{(-?\d+)\}/g,
        (_m, base, exp) => `$${base}^{${exp}}$`,
      );
      fixed = fixed.replace(
        /(\d+)\^(-?\d+)/g,
        (_m, base, exp) => `$${base}^{${exp}}$`,
      );
      return fixed;
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
