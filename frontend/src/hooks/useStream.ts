import { streamChat } from "../api/chat";
import { useChatStore } from "../store/chatStore";

export function useStream() {
  const chatStore = useChatStore();

  const sendMessage = (
    message: string,
    conversationId: string | null,
    ragEnabled: boolean,
  ) => {
    chatStore.setIsStreaming(true);
    chatStore.clearStreamingMessage();

    const cleanup = streamChat(
      message,
      conversationId,
      ragEnabled,
      (chunk) => {
        if (chunk.type === "token") {
          chatStore.appendToken(String(chunk.data));
        } else if (chunk.type === "tool_call") {
          const payload = chunk.data as { name: string; input: Record<string, unknown> };
          chatStore.addToolCall({
            name: payload.name,
            input: payload.input ?? {},
            status: "running",
          });
        } else if (chunk.type === "tool_result") {
          const payload = chunk.data as { name: string; output: string };
          chatStore.updateToolCall(payload.name, payload.output ?? "");
        } else if (chunk.type === "done") {
          const payload = chunk.data as { conversation_id: string; message_id: string };
          const convId = String(payload.conversation_id);
          void (async () => {
            chatStore.clearPendingMessages();
            await chatStore.loadHistory(convId);
            await chatStore.loadConversations();
            chatStore.setActiveConversation(convId);
            chatStore.clearStreamingMessage();
            chatStore.setIsStreaming(false);
          })();
        } else if (chunk.type === "error") {
          const msg =
            typeof chunk.data === "string" ? chunk.data : JSON.stringify(chunk.data);
          console.error(msg);
          chatStore.setIsStreaming(false);
        }
      },
      () => {
        /* handled in done chunk */
      },
      (err) => {
        console.error(err);
        chatStore.setIsStreaming(false);
      },
    );

    return cleanup;
  };

  return { sendMessage };
}
