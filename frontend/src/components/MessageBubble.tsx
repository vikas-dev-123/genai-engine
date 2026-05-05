import { ReactNode, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import clsx from "clsx";

import type { Message } from "../types";

import { ToolCallCard } from "./ToolCallCard";

import "highlight.js/styles/github-dark.css";

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

const sourcePattern = /(\[Source:[^\]]+\])/g;

function decorateCitations(children: ReactNode): ReactNode {
  if (typeof children === "string") {
    const parts = children.split(sourcePattern);
    return parts.map((part, idx) =>
      part.startsWith("[Source:") ? (
        <span
          key={`src-${idx.toString()}`}
          className="mx-0.5 rounded bg-jarvis-teal/15 px-1 text-[11px] text-jarvis-teal"
        >
          {part}
        </span>
      ) : (
        part
      ),
    );
  }
  return children;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (isUser) {
    return (
      <div className="flex justify-end gap-3">
        <div
          className={clsx(
            "max-w-[80%] rounded-2xl rounded-br-sm bg-jarvis-accent px-4 py-3 text-sm text-white shadow-lg",
            isStreaming && "animate-pulse",
          )}
        >
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
        <div className="mt-1 h-9 w-9 rounded-full bg-jarvis-accent/40 text-center text-sm font-semibold leading-9 text-white">
          U
        </div>
      </div>
    );
  }

  return (
    <div className="group flex gap-3">
      <div className="mt-1 flex h-9 w-9 items-center justify-center rounded-full bg-jarvis-accent text-sm font-bold text-white">
        J
      </div>
      <div className="max-w-[85%] flex-1 rounded-2xl rounded-bl-sm border border-jarvis-border bg-jarvis-surface px-4 py-3 text-sm text-jarvis-text shadow-inner">
        <div className="prose prose-invert max-w-none prose-pre:bg-black/40 prose-pre:border prose-pre:border-jarvis-border">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={{
              p: ({ children }) => <p>{decorateCitations(children as ReactNode)}</p>,
              li: ({ children }) => <li>{decorateCitations(children as ReactNode)}</li>,
              code: ({
                className,
                children,
                ...rest
              }: {
                className?: string;
                children?: ReactNode;
                inline?: boolean;
              }) => {
                const inline = Boolean(rest.inline);
                const text = String(children);
                const lang = /language-([\w-]+)/.exec(className ?? "")?.[1];
                if (inline) {
                  return (
                    <code className="rounded bg-black/50 px-1 py-0.5 text-xs text-jarvis-teal">
                      {text}
                    </code>
                  );
                }
                return (
                  <div className="relative my-2 overflow-hidden rounded-lg border border-jarvis-border bg-black/60">
                    <div className="flex items-center justify-between px-3 py-1 text-[10px] uppercase tracking-wide text-jarvis-muted">
                      <span>{lang ?? "code"}</span>
                      <button
                        type="button"
                        className="rounded border border-jarvis-border px-2 py-0.5 text-[10px] text-jarvis-text hover:bg-jarvis-surface"
                        onClick={() => void navigator.clipboard.writeText(text)}
                      >
                        Copy
                      </button>
                    </div>
                    <pre className="overflow-auto p-3 text-xs">
                      <code className={className}>{text}</code>
                    </pre>
                  </div>
                );
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
        {message.tool_calls?.length ? (
          <div className="mt-3 space-y-2">
            {message.tool_calls.map((tc) => (
              <ToolCallCard
                key={`${tc.name}-${tc.output ?? "run"}`}
                toolCall={{
                  name: tc.name,
                  input: tc.input,
                  output: tc.output,
                  status: tc.output ? "done" : "running",
                }}
              />
            ))}
          </div>
        ) : null}
        <div className="mt-2 flex items-center justify-between text-[10px] text-jarvis-muted opacity-0 transition group-hover:opacity-100">
          <span>{new Date(message.created_at).toLocaleString()}</span>
          <button type="button" onClick={() => void handleCopy()} className="hover:text-jarvis-text">
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
    </div>
  );
}
