import { create } from "zustand";

import { deleteDocument as apiDeleteDoc, listDocuments as apiListDocs } from "../api/rag";
import type { Conversation, DocumentInfo, Message, ToolCall } from "../types";

import { deleteConversation as apiDeleteConv, getConversations, getHistory } from "../api/chat";

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  messages: Record<string, Message[]>;
  streamingMessage: string | null;
  activeToolCalls: ToolCall[];
  ragEnabled: boolean;
  voiceMode: boolean;
  isStreaming: boolean;
  documents: DocumentInfo[];
  loadConversations: () => Promise<void>;
  loadHistory: (conversationId: string) => Promise<void>;
  newConversation: () => void;
  setActiveConversation: (id: string) => void;
  appendToken: (token: string) => void;
  addToolCall: (call: ToolCall) => void;
  updateToolCall: (name: string, output: string) => void;
  finalizeMessage: (conversationId: string, messageId: string) => void;
  clearStreamingMessage: () => void;
  setIsStreaming: (val: boolean) => void;
  setRagEnabled: (val: boolean) => void;
  setVoiceMode: (val: boolean) => void;
  addDocument: (doc: DocumentInfo) => void;
  loadDocuments: () => Promise<void>;
  deleteDocument: (docId: string) => Promise<void>;
  deleteConversationById: (id: string) => Promise<void>;
  addOptimisticUserMessage: (conversationId: string | null, content: string) => void;
  updateConversationTitle: (id: string, title: string) => void;
  clearPendingMessages: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: {},
  streamingMessage: null,
  activeToolCalls: [],
  ragEnabled: true,
  voiceMode: false,
  isStreaming: false,
  documents: [],

  loadConversations: async () => {
    const rows = await getConversations();
    set({ conversations: rows });
  },

  loadHistory: async (conversationId: string) => {
    const msgs = await getHistory(conversationId);
    set((state) => ({
      messages: { ...state.messages, [conversationId]: msgs },
    }));
  },

  newConversation: () => {
    set((state) => {
      const next = { ...state.messages };
      delete next.pending;
      return {
        activeConversationId: null,
        streamingMessage: null,
        activeToolCalls: [],
        messages: next,
      };
    });
  },

  setActiveConversation: (id: string) => {
    set({ activeConversationId: id, streamingMessage: null, activeToolCalls: [] });
  },

  appendToken: (token: string) => {
    set((state) => ({
      streamingMessage: (state.streamingMessage ?? "") + token,
    }));
  },

  addToolCall: (call: ToolCall) => {
    set((state) => ({
      activeToolCalls: [...state.activeToolCalls.filter((c) => c.name !== call.name), call],
    }));
  },

  updateToolCall: (name: string, output: string) => {
    set((state) => ({
      activeToolCalls: state.activeToolCalls.map((c) =>
        c.name === name ? { ...c, output, status: "done" as const } : c,
      ),
    }));
  },

  finalizeMessage: (conversationId, messageId) => {
    const state = get();
    const text = state.streamingMessage ?? "";
    const tools = state.activeToolCalls.length ? [...state.activeToolCalls] : null;
    const assistantMsg: Message = {
      id: messageId,
      conversation_id: conversationId,
      role: "assistant",
      content: text,
      tool_calls: tools,
      created_at: new Date().toISOString(),
    };
    set((s) => {
      const existing = s.messages[conversationId] ?? [];
      return {
        messages: {
          ...s.messages,
          [conversationId]: [...existing, assistantMsg],
        },
        streamingMessage: null,
        activeToolCalls: [],
        activeConversationId: conversationId,
      };
    });
    void get().loadConversations();
  },

  clearStreamingMessage: () => {
    set({ streamingMessage: null, activeToolCalls: [] });
  },

  setIsStreaming: (val: boolean) => {
    set({ isStreaming: val });
  },

  setRagEnabled: (val: boolean) => {
    set({ ragEnabled: val });
  },

  setVoiceMode: (val: boolean) => {
    set({ voiceMode: val });
  },

  addDocument: (doc: DocumentInfo) => {
    set((state) => ({
      documents: [doc, ...state.documents.filter((d) => d.id !== doc.id)],
    }));
  },

  loadDocuments: async () => {
    const docs = await apiListDocs();
    set({ documents: docs });
  },

  deleteDocument: async (docId: string) => {
    await apiDeleteDoc(docId);
    set((state) => ({
      documents: state.documents.filter((d) => d.id !== docId),
    }));
  },

  deleteConversationById: async (id: string) => {
    await apiDeleteConv(id);
    set((state) => {
      const nextMsgs = { ...state.messages };
      delete nextMsgs[id];
      return {
        conversations: state.conversations.filter((c) => c.id !== id),
        messages: nextMsgs,
        activeConversationId: state.activeConversationId === id ? null : state.activeConversationId,
      };
    });
  },

  addOptimisticUserMessage: (conversationId, content) => {
    const key = conversationId ?? "pending";
    const optimistic: Message = {
      id: `tmp-${Date.now()}`,
      conversation_id: conversationId ?? "pending",
      role: "user",
      content,
      tool_calls: null,
      created_at: new Date().toISOString(),
    };
    set((state) => {
      const existing = state.messages[key] ?? [];
      return {
        messages: {
          ...state.messages,
          [key]: [...existing, optimistic],
        },
      };
    });
  },

  clearPendingMessages: () => {
    set((state) => {
      const next = { ...state.messages };
      delete next.pending;
      return { messages: next };
    });
  },

  updateConversationTitle: (id, title) => {
    set((state) => ({
      conversations: state.conversations.map((c) => (c.id === id ? { ...c, title } : c)),
    }));
  },
}));
