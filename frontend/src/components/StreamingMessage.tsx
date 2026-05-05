import { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import clsx from "clsx";

import { useChatStore } from "../store/chatStore";

import { ToolCallCard } from "./ToolCallCard";

import "highlight.js/styles/github-dark.css";

const sourcePattern = /(\[Source:[^\]]+\])/g;

function decorateCitations(children: ReactNode): ReactNode {
  if (typeof children === "string") {
    const parts = children.split(sourcePattern);
    return parts.map((part, idx) =>
      part.startsWith("[Source:") ? (
        <span
          key={`s-${idx.toString()}`}
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

export function StreamingMessage() {
  const streamingMessage = useChatStore((s) => s.streamingMessage);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const activeToolCalls = useChatStore((s) => s.activeToolCalls);

  if (!isStreaming) {
    return null;
  }

  return (
    <div className="flex gap-3">
      <div className="mt-1 flex h-9 w-9 items-center justify-center rounded-full bg-jarvis-accent text-sm font-bold text-white">
        J
      </div>
      <div className="max-w-[85%] flex-1 rounded-2xl rounded-bl-sm border border-jarvis-border bg-jarvis-surface px-4 py-3 text-sm text-jarvis-text shadow-inner">
        {activeToolCalls.length > 0 && (
          <div className="mb-3 space-y-2">
            {activeToolCalls.map((tc) => (
              <ToolCallCard key={`${tc.name}-stream`} toolCall={tc} />
            ))}
          </div>
        )}
        {!streamingMessage && (
          <div className="flex items-center gap-1 py-2 text-jarvis-muted">
            <span className="typing-dot inline-block h-2 w-2 rounded-full bg-jarvis-accent" />
            <span className="typing-dot inline-block h-2 w-2 rounded-full bg-jarvis-accent" />
            <span className="typing-dot inline-block h-2 w-2 rounded-full bg-jarvis-accent" />
          </div>
        )}
        {streamingMessage && (
          <div className="prose prose-invert max-w-none prose-pre:bg-black/40">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
              components={{
                p: ({ children }) => <p>{decorateCitations(children as ReactNode)}</p>,
                li: ({ children }) => <li>{decorateCitations(children as ReactNode)}</li>,
              }}
            >
              {streamingMessage}
            </ReactMarkdown>
            <span className="blinking-cursor inline-block w-2 translate-y-1" />
          </div>
        )}
        <div className={clsx("mt-2 h-1 w-24 rounded-full bg-jarvis-border", isStreaming && "animate-pulse")} />
      </div>
    </div>
  );
}
