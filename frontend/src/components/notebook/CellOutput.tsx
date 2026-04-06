"use client";

import { useMemo } from "react";
import type { CellOutput as CellOutputType } from "@/lib/types";
import AnsiToHtml from "ansi-to-html";

const ansiConverter = new AnsiToHtml({ escapeXML: true });

interface Props {
  outputs: CellOutputType[];
}

function SingleOutput({ output }: { output: CellOutputType }) {
  if (output.output_type === "stream") {
    return (
      <pre className="bg-gray-50 text-sm font-mono p-3 whitespace-pre-wrap overflow-x-auto">
        {output.text}
      </pre>
    );
  }

  if (output.output_type === "error") {
    const html = (output.traceback ?? [])
      .map((line) => ansiConverter.toHtml(line))
      .join("\n");
    return (
      <pre
        className="bg-red-50 text-sm font-mono p-3 whitespace-pre-wrap overflow-x-auto text-red-800"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  }

  // execute_result or display_data
  const data = output.data;
  if (!data) return null;

  if (data["text/html"]) {
    return (
      <div
        className="overflow-x-auto p-3 text-sm"
        dangerouslySetInnerHTML={{ __html: data["text/html"] }}
      />
    );
  }

  if (data["image/png"]) {
    return (
      <div className="p-3">
        <img src={`data:image/png;base64,${data["image/png"]}`} alt="output" />
      </div>
    );
  }

  if (data["text/plain"]) {
    return (
      <pre className="bg-gray-50 text-sm font-mono p-3 whitespace-pre-wrap overflow-x-auto">
        {data["text/plain"]}
      </pre>
    );
  }

  return null;
}

export default function CellOutput({ outputs }: Props) {
  const filtered = useMemo(
    () => outputs.filter((o) => o.text || o.data || o.traceback),
    [outputs]
  );

  if (filtered.length === 0) return null;

  return (
    <div className="border-t border-gray-100">
      {filtered.map((output, i) => (
        <SingleOutput key={i} output={output} />
      ))}
    </div>
  );
}
