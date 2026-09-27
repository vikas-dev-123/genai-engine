import { useEffect, useMemo, useState } from "react";
import { LogOut, MessageSquarePlus, Trash2, Upload } from "lucide-react";

import { useAuthStore } from "../store/authStore";
import { useChatStore } from "../store/chatStore";

import { DocumentUpload } from "./DocumentUpload";

function formatRelative(dateIso: string) {
  const diff = Date.now() - new Date(dateIso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const conversations = useChatStore((s) => s.conversations);
  const activeId = useChatStore((s) => s.activeConversationId);
  const loadConversations = useChatStore((s) => s.loadConversations);
  const setActive = useChatStore((s) => s.setActiveConversation);
  const newConversation = useChatStore((s) => s.newConversation);
  const loadHistory = useChatStore((s) => s.loadHistory);
  const deleteConversationById = useChatStore((s) => s.deleteConversationById);
  const ragEnabled = useChatStore((s) => s.ragEnabled);
  const setRagEnabled = useChatStore((s) => s.setRagEnabled);
  const documents = useChatStore((s) => s.documents);
  const loadDocuments = useChatStore((s) => s.loadDocuments);

  const [uploadOpen, setUploadOpen] = useState(false);

  useEffect(() => {
    void loadConversations();
    void loadDocuments();
  }, [loadConversations, loadDocuments]);

  const initials = useMemo(() => {
    if (!user?.name) {
      return "J";
    }
    const parts = user.name.split(" ");
    const first = parts[0]?.[0] ?? "";
    const last = parts[1]?.[0] ?? "";
    return (first + last).toUpperCase() || "J";
  }, [user?.name]);

  return (
    <aside className="flex h-full w-72 flex-col border-r border-engine-border bg-engine-surface">
      <div className="border-b border-engine-border px-4 py-4">
        <div className="text-xs font-semibold tracking-[0.35em] text-engine-accent">GENAI ENGINE</div>
        <div className="text-[10px] text-engine-muted">v1.0.0</div>
        <button
          type="button"
          onClick={() => newConversation()}
          className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg bg-engine-accent/20 py-2 text-sm font-medium text-engine-text hover:bg-engine-accent/30"
        >
          <MessageSquarePlus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
        <div>
          <p className="px-1 text-[11px] font-semibold uppercase tracking-wide text-engine-muted">
            Conversations
          </p>
          <div className="mt-2 space-y-1">
            {conversations.map((c) => (
              <div
                key={c.id}
                className={`group flex items-center gap-2 rounded-lg border px-2 py-2 text-xs ${
                  activeId === c.id
                    ? "border-engine-accent/60 bg-engine-accent/10"
                    : "border-transparent hover:border-engine-border hover:bg-engine-bg"
                }`}
              >
                <button
                  type="button"
                  onClick={() => {
                    void loadHistory(c.id);
                    setActive(c.id);
                  }}
                  className="flex-1 text-left"
                >
                  <div className="truncate font-medium text-engine-text">{c.title}</div>
                  <div className="text-[10px] text-engine-muted">
                    {formatRelative(c.updated_at)} · {c.message_count} msgs
                  </div>
                </button>
                <button
                  type="button"
                  className="hidden rounded-md p-1 text-engine-muted hover:text-engine-danger group-hover:inline-flex"
                  onClick={() => void deleteConversationById(c.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between px-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-engine-muted">
              Knowledge Base
            </p>
            <label className="flex items-center gap-2 text-[11px] text-engine-text">
              <span>RAG</span>
              <input
                type="checkbox"
                className="accent-engine-accent"
                checked={ragEnabled}
                onChange={(e) => setRagEnabled(e.target.checked)}
              />
            </label>
          </div>
          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-engine-border py-2 text-xs text-engine-muted hover:border-engine-accent hover:text-engine-text"
          >
            <Upload className="h-4 w-4" />
            Upload Document
          </button>
          <div className="mt-2 space-y-1">
            {documents.map((doc) => (
              <div key={doc.id} className="rounded-md border border-engine-border bg-engine-bg px-2 py-1 text-[11px]">
                <div className="truncate text-engine-text">{doc.filename}</div>
                <div className="flex items-center justify-between text-[10px] text-engine-muted">
                  <span>{doc.file_size_bytes ? (doc.file_size_bytes / 1024).toFixed(0) : "0"} KB</span>
                  <span
                    className={
                      doc.status === "ready" ? "text-engine-teal" : "text-amber-300"
                    }
                  >
                    {doc.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="border-t border-engine-border px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-engine-accent text-sm font-semibold text-white">
            {initials}
          </div>
          <div className="flex-1 overflow-hidden">
            <div className="truncate text-sm font-medium text-engine-text">{user?.name}</div>
            <div className="truncate text-[11px] text-engine-muted">{user?.email}</div>
          </div>
          <button
            type="button"
            onClick={() => logout()}
            className="rounded-md border border-engine-border p-2 text-engine-muted hover:text-engine-danger"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>

      <DocumentUpload isOpen={uploadOpen} onClose={() => setUploadOpen(false)} />
    </aside>
  );
}
