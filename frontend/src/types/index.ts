export interface User {
  id: string;
  email: string;
  name: string;
  timezone: string;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  tool_calls: ToolCall[] | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  output?: string;
  status: "running" | "done" | "error";
}

export interface StreamChunk {
  type: "token" | "tool_call" | "tool_result" | "done" | "error";
  data: string | Record<string, unknown>;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number | null;
  num_chunks: number;
  status: "processing" | "ready" | "failed";
  created_at: string;
}

export interface ChunkResult {
  content: string;
  filename: string;
  page_number: number | null;
  similarity_score: number;
  chunk_index: number;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}
