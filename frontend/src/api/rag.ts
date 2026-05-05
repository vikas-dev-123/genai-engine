import apiClient from "./client";
import type { ChunkResult, DocumentInfo } from "../types";

export async function uploadDocument(
  file: File,
  onProgress: (pct: number) => void,
): Promise<DocumentInfo> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await apiClient.post<DocumentInfo>("/rag/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (evt) => {
      if (evt.total) {
        onProgress(Math.round((evt.loaded / evt.total) * 100));
      }
    },
  });
  return data;
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  const { data } = await apiClient.get<DocumentInfo[]>("/rag/documents");
  return data;
}

export async function deleteDocument(docId: string): Promise<void> {
  await apiClient.delete(`/rag/document/${docId}`);
}

export async function searchDocuments(query: string): Promise<ChunkResult[]> {
  const { data } = await apiClient.get<{ chunks: ChunkResult[] }>("/rag/search", {
    params: { q: query },
  });
  return data.chunks;
}
