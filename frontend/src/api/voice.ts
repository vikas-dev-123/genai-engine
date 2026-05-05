import apiClient from "./client";

export async function transcribe(
  audioBlob: Blob,
): Promise<{ transcript: string; language: string; confidence: number; duration_seconds: number }> {
  const form = new FormData();
  form.append("file", audioBlob, "audio.webm");
  const { data } = await apiClient.post("/voice/transcribe", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data as {
    transcript: string;
    language: string;
    confidence: number;
    duration_seconds: number;
  };
}

export async function synthesize(text: string): Promise<Blob> {
  const { data } = await apiClient.post("/voice/synthesize", { text }, { responseType: "blob" });
  return data as Blob;
}
