import { getApiBasePath } from "../env";
import { useAuthStore } from "../store/authStore";
import type { Conversation, Message, StreamChunk } from "../types";

import apiClient from "./client";

export function streamChat(
  message: string,
  conversationId: string | null,
  ragEnabled: boolean,
  onChunk: (chunk: StreamChunk) => void,
  onDone: () => void,
  onError: (err: string) => void,
): () => void {
  const controller = new AbortController();
  const run = async () => {
    const token = useAuthStore.getState().accessToken;
    if (!token) {
      onError("Not authenticated");
      return;
    }
    let finished = false;
    const finish = () => {
      if (!finished) {
        finished = true;
        onDone();
      }
    };
    try {
      const response = await fetch(`${getApiBasePath()}/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message,
          conversation_id: conversationId,
          rag_enabled: ragEnabled,
        }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        onError(`Request failed (${response.status})`);
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (value) {
          buffer += decoder.decode(value, { stream: true });
        }
        const segments = buffer.split("\n\n");
        buffer = segments.pop() ?? "";
        for (const segment of segments) {
          const line = segment.trim();
          if (!line.startsWith("data:")) {
            continue;
          }
          const jsonText = line.slice(5).trim();
          try {
            const parsed = JSON.parse(jsonText) as StreamChunk;
            onChunk(parsed);
            if (parsed.type === "error") {
              const msg =
                typeof parsed.data === "string"
                  ? parsed.data
                  : JSON.stringify(parsed.data);
              onError(msg);
              return;
            }
            if (parsed.type === "done") {
              finish();
              return;
            }
          } catch {
            onError("Failed to parse stream chunk");
            return;
          }
        }
        if (done) {
          break;
        }
      }
      if (buffer.trim()) {
        const line = buffer.trim();
        if (line.startsWith("data:")) {
          const jsonText = line.slice(5).trim();
          try {
            const parsed = JSON.parse(jsonText) as StreamChunk;
            onChunk(parsed);
            if (parsed.type === "error") {
              const msg =
                typeof parsed.data === "string"
                  ? parsed.data
                  : JSON.stringify(parsed.data);
              onError(msg);
              return;
            }
            if (parsed.type === "done") {
              finish();
              return;
            }
          } catch {
            onError("Failed to parse trailing stream chunk");
            return;
          }
        }
      }
      finish();
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        return;
      }
      onError((err as Error).message || "Stream error");
    }
  };
  void run();
  return () => controller.abort();
}

export async function getConversations(): Promise<Conversation[]> {
  const { data } = await apiClient.get<Conversation[]>("/chat/conversations");
  return data;
}

export async function getHistory(conversationId: string): Promise<Message[]> {
  const { data } = await apiClient.get<Message[]>(`/chat/history/${conversationId}`);
  return data;
}

export async function deleteConversation(id: string): Promise<void> {
  await apiClient.delete(`/chat/conversation/${id}`);
}
