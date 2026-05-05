import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { useStream } from "../hooks/useStream";
import { useChatStore } from "../store/chatStore";

import { MessageBubble } from "./MessageBubble";
import { StreamingMessage } from "./StreamingMessage";
import { VoiceButton } from "./VoiceButton";

const SUGGESTIONS = [
  "Summarize my uploaded documents.",
  "What changed in AI regulations lately?",
  "Draft a polite follow-up email.",
];

export function ChatWindow() {
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const messagesMap = useChatStore((s) => s.messages);
  const ragEnabled = useChatStore((s) => s.ragEnabled);
  const voiceMode = useChatStore((s) => s.voiceMode);
  const setVoiceMode = useChatStore((s) => s.setVoiceMode);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const addOptimistic = useChatStore((s) => s.addOptimisticUserMessage);
  const updateTitle = useChatStore((s) => s.updateConversationTitle);
  const conversations = useChatStore((s) => s.conversations);

  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const { sendMessage } = useStream();

  const title = useMemo(() => {
    if (!activeConversationId) {
      return "New conversation";
    }
    return conversations.find((c) => c.id === activeConversationId)?.title ?? "Conversation";
  }, [activeConversationId, conversations]);

  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(title);

  useEffect(() => {
    setTitleDraft(title);
  }, [title]);

  const listMessages = useMemo(() => {
    if (activeConversationId) {
      return messagesMap[activeConversationId] ?? [];
    }
    return messagesMap.pending ?? [];
  }, [activeConversationId, messagesMap]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [listMessages, isStreaming]);

  const cleanupRef = useRef<(() => void) | null>(null);

  const handleSubmit = async (evt: FormEvent) => {
    evt.preventDefault();
    const text = input.trim();
    if (!text || isStreaming) {
      return;
    }
    addOptimistic(activeConversationId, text);
    setInput("");
    cleanupRef.current?.();
    cleanupRef.current = sendMessage(text, activeConversationId, ragEnabled);
  };

  const onSuggestion = (text: string) => {
    setInput(text);
  };

  return (
    <div className="flex h-full flex-1 flex-col bg-jarvis-bg">
      <header className="flex items-center justify-between border-b border-jarvis-border px-6 py-3">
        <div>
          {editingTitle ? (
            <input
              className="rounded-md border border-jarvis-border bg-jarvis-surface px-2 py-1 text-sm text-jarvis-text"
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onBlur={() => {
                setEditingTitle(false);
                if (activeConversationId) {
                  updateTitle(activeConversationId, titleDraft.slice(0, 200));
                }
              }}
            />
          ) : (
            <button
              type="button"
              className="text-left text-sm font-semibold text-jarvis-text"
              onClick={() => setEditingTitle(true)}
            >
              {title}
            </button>
          )}
          <div className="mt-1 flex items-center gap-2 text-[11px] text-jarvis-muted">
            <span className={`h-2 w-2 rounded-full ${ragEnabled ? "bg-jarvis-teal" : "bg-jarvis-muted"}`} />
            RAG {ragEnabled ? "on" : "off"}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setVoiceMode(!voiceMode)}
          className={`rounded-full border px-3 py-1 text-xs ${
            voiceMode ? "border-jarvis-accent text-jarvis-accent" : "border-jarvis-border text-jarvis-muted"
          }`}
        >
          Voice mode
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {listMessages.length === 0 && !isStreaming && (
          <div className="flex h-full flex-col items-center justify-center text-center text-jarvis-muted">
            <div className="mb-4 text-lg font-semibold text-jarvis-accent">JARVIS</div>
            <p className="mb-6 text-sm text-jarvis-text">How can I help you today?</p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onSuggestion(s)}
                  className="rounded-full border border-jarvis-border px-3 py-1 text-xs text-jarvis-text hover:border-jarvis-accent"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {listMessages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        <StreamingMessage />
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(e) => void handleSubmit(e)}
        className="border-t border-jarvis-border bg-jarvis-surface/40 px-4 py-3 backdrop-blur"
      >
        <div className="flex items-end gap-3">
          <VoiceButton onTranscript={(t) => setInput((prev) => `${prev} ${t}`.trim())} />
          <div className="flex-1">
            <textarea
              className="w-full resize-none rounded-xl border border-jarvis-border bg-jarvis-bg px-3 py-2 text-sm text-jarvis-text outline-none focus:border-jarvis-accent"
              rows={Math.min(5, Math.max(2, input.split("\n").length))}
              placeholder="Message Jarvis..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handleSubmit(e as unknown as FormEvent);
                }
              }}
              disabled={isStreaming}
            />
            {input.length > 1000 && (
              <div className="mt-1 text-right text-[11px] text-jarvis-muted">{input.length} characters</div>
            )}
          </div>
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className="rounded-xl bg-jarvis-accent px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-jarvis-accent/30 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
