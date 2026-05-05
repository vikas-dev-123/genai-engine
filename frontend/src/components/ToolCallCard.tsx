import { useState } from "react";
import {
  CheckCircle2,
  FilePlus,
  FileText,
  Globe,
  Loader2,
  Search,
  Terminal,
  XCircle,
} from "lucide-react";

import type { ToolCall } from "../types";

const iconFor = (name: string) => {
  switch (name) {
    case "web_search":
      return Search;
    case "file_read":
      return FileText;
    case "file_write":
      return FilePlus;
    case "api_call":
      return Globe;
    case "system_command":
      return Terminal;
    default:
      return Terminal;
  }
};

interface ToolCallCardProps {
  toolCall: ToolCall;
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  const [open, setOpen] = useState(false);
  const Icon = iconFor(toolCall.name);
  const isRunning = toolCall.status === "running";
  const isError = toolCall.status === "error";

  const inputPreview = JSON.stringify(toolCall.input).slice(0, 160);
  const outputPreview = (toolCall.output ?? "").slice(0, 200);

  return (
    <div className="mt-2 rounded-lg border border-jarvis-border bg-jarvis-bg/70 p-3 text-xs text-jarvis-muted">
      <div className="flex items-center gap-2">
        {isRunning ? (
          <Loader2 className="h-4 w-4 animate-spin text-jarvis-accent" />
        ) : isError ? (
          <XCircle className="h-4 w-4 text-jarvis-danger" />
        ) : (
          <CheckCircle2 className="h-4 w-4 text-jarvis-teal" />
        )}
        <Icon className="h-4 w-4 text-jarvis-accent" />
        <span className="font-semibold text-jarvis-text">{toolCall.name}</span>
      </div>
      {isRunning && <p className="mt-1 truncate text-[11px] text-jarvis-muted">{inputPreview}</p>}
      {!isRunning && toolCall.output !== undefined && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="mt-2 w-full rounded-md border border-jarvis-border px-2 py-1 text-left text-[11px] text-jarvis-text hover:bg-jarvis-surface"
        >
          {open ? "Hide output" : "Show output"} — {outputPreview}
          {!open && toolCall.output && toolCall.output.length > 200 ? "…" : ""}
        </button>
      )}
      {open && (
        <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-black/40 p-2 text-[11px] text-jarvis-text">
          {toolCall.output}
        </pre>
      )}
    </div>
  );
}
