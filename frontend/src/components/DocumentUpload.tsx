import { type DragEvent, useEffect, useRef, useState } from "react";
import { Trash2, UploadCloud, X } from "lucide-react";

import { listDocuments, uploadDocument } from "../api/rag";
import { useChatStore } from "../store/chatStore";

interface DocumentUploadProps {
  isOpen: boolean;
  onClose: () => void;
}

export function DocumentUpload({ isOpen, onClose }: DocumentUploadProps) {
  const addDocument = useChatStore((s) => s.addDocument);
  const documents = useChatStore((s) => s.documents);
  const loadDocuments = useChatStore((s) => s.loadDocuments);
  const removeFromStore = useChatStore((s) => s.deleteDocument);

  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState<string | null>(null);
  const polling = useRef<number | null>(null);

  useEffect(() => {
    if (isOpen) {
      void loadDocuments();
    }
  }, [isOpen, loadDocuments]);

  useEffect(
    () => () => {
      if (polling.current) {
        window.clearInterval(polling.current);
      }
    },
    [],
  );

  if (!isOpen) {
    return null;
  }

  const validateFile = (file: File) => {
    const name = file.name.toLowerCase();
    const ok = name.endsWith(".pdf") || name.endsWith(".txt") || name.endsWith(".docx") || name.endsWith(".md");
    if (!ok) {
      return "Only PDF, TXT, DOCX, or MD files are supported.";
    }
    if (file.size > 50 * 1024 * 1024) {
      return "File must be 50MB or smaller.";
    }
    return null;
  };

  const startPolling = () => {
    if (polling.current) {
      window.clearInterval(polling.current);
    }
    polling.current = window.setInterval(() => {
      void listDocuments().then((docs) => {
        useChatStore.setState({ documents: docs });
        const busy = docs.some((d) => d.status === "processing");
        if (!busy && polling.current) {
          window.clearInterval(polling.current);
          polling.current = null;
          setStatusText(null);
        }
      });
    }, 4000);
  };

  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) {
      return;
    }
    const file = fileList[0];
    const validation = validateFile(file);
    if (validation) {
      setError(validation);
      return;
    }
    setError(null);
    setProgress(0);
    setStatusText("Uploading…");
    try {
      const doc = await uploadDocument(file, (pct) => setProgress(pct));
      addDocument(doc);
      setStatusText("Processing chunks…");
      startPolling();
    } catch {
      setError("Upload failed. Please try again.");
      setStatusText(null);
    }
  };

  const onDrop = (evt: DragEvent<HTMLDivElement>) => {
    evt.preventDefault();
    setDragActive(false);
    void handleFiles(evt.dataTransfer.files);
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm">
      <div className="w-full max-w-xl rounded-2xl border border-jarvis-border bg-jarvis-surface p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-jarvis-text">Knowledge Base Upload</h3>
          <button type="button" onClick={onClose} className="rounded-full p-1 text-jarvis-muted hover:text-jarvis-text">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div
          onDragEnter={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragOver={(e) => e.preventDefault()}
          onDragLeave={() => setDragActive(false)}
          onDrop={onDrop}
          className={`flex flex-col items-center justify-center rounded-xl border border-dashed px-4 py-10 text-center transition ${
            dragActive ? "border-jarvis-accent bg-jarvis-accent/5" : "border-jarvis-border bg-jarvis-bg"
          }`}
        >
          <UploadCloud className="mb-3 h-10 w-10 text-jarvis-accent" />
          <p className="text-sm text-jarvis-text">Drop PDF, TXT, DOCX, or MD files here</p>
          <p className="text-xs text-jarvis-muted">or click to browse</p>
          <label className="mt-4 cursor-pointer rounded-md bg-jarvis-accent px-4 py-2 text-sm font-medium text-white">
            Browse
            <input
              type="file"
              className="hidden"
              accept=".pdf,.txt,.docx,.md"
              onChange={(e) => void handleFiles(e.target.files)}
            />
          </label>
        </div>

        {error && <p className="mt-3 text-sm text-jarvis-danger">{error}</p>}

        {statusText && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between text-xs text-jarvis-muted">
              <span>{statusText}</span>
              <span>{progress}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-jarvis-border">
              <div className="h-full bg-jarvis-accent transition-all" style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}

        <div className="mt-6 space-y-2">
          <p className="text-xs uppercase tracking-wide text-jarvis-muted">Uploaded</p>
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="flex items-center justify-between rounded-lg border border-jarvis-border bg-jarvis-bg px-3 py-2 text-xs text-jarvis-text"
            >
              <div>
                <div className="font-medium">{doc.filename}</div>
                <div className="text-[10px] text-jarvis-muted">
                  {doc.file_type.toUpperCase()} · {doc.num_chunks} chunks ·{" "}
                  {new Date(doc.created_at).toLocaleString()}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] ${
                    doc.status === "ready"
                      ? "bg-jarvis-teal/20 text-jarvis-teal"
                      : doc.status === "processing"
                        ? "bg-amber-500/20 text-amber-300"
                        : "bg-jarvis-danger/20 text-jarvis-danger"
                  }`}
                >
                  {doc.status}
                </span>
                <button
                  type="button"
                  className="rounded-md border border-jarvis-border p-1 text-jarvis-muted hover:text-jarvis-danger"
                  onClick={() => {
                    if (window.confirm(`Delete ${doc.filename}?`)) {
                      void removeFromStore(doc.id);
                    }
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
