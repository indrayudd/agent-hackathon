"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

interface StoryMarkdownProps {
  content: string;
  className?: string;
}

export default function StoryMarkdown({ content, className }: StoryMarkdownProps) {
  return (
    <div className={`report-prose prose prose-sm max-w-none text-on-surface-variant ${className || ""}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
