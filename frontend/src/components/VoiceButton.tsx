import { useCallback, useEffect, useState } from "react";
import { Loader2, Mic } from "lucide-react";
import clsx from "clsx";

import { useVoice } from "../hooks/useVoice";

interface VoiceButtonProps {
  onTranscript: (text: string) => void;
}

export function VoiceButton({ onTranscript }: VoiceButtonProps) {
  const { isRecording, isProcessing, transcript, waveformData, startRecording, stopRecording, clearTranscript } =
    useVoice();
  const [toggleOn, setToggleOn] = useState(false);

  useEffect(() => {
    if (transcript) {
      onTranscript(transcript);
      clearTranscript();
    }
  }, [transcript, onTranscript, clearTranscript]);

  const handleToggle = useCallback(async () => {
    if (isProcessing) {
      return;
    }
    if (!isRecording) {
      setToggleOn(true);
      await startRecording();
    } else {
      setToggleOn(false);
      await stopRecording();
    }
  }, [isProcessing, isRecording, startRecording, stopRecording]);

  useEffect(() => {
    const onKey = (evt: KeyboardEvent) => {
      const target = evt.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) {
        return;
      }
      if (evt.code === "Space") {
        evt.preventDefault();
        void handleToggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleToggle]);

  return (
    <div className="flex flex-col items-center gap-2">
      <button
        type="button"
        onClick={() => void handleToggle()}
        className={clsx(
          "relative flex h-12 w-12 items-center justify-center rounded-full border-2 transition",
          isRecording
            ? "border-jarvis-danger shadow-[0_0_18px_rgba(255,71,87,0.55)]"
            : "border-jarvis-border hover:border-jarvis-accent",
          toggleOn && isRecording && "animate-pulse",
        )}
      >
        {isProcessing ? (
          <Loader2 className="h-5 w-5 animate-spin text-jarvis-accent" />
        ) : (
          <Mic className={clsx("h-5 w-5", isRecording ? "text-jarvis-danger" : "text-jarvis-text")} />
        )}
      </button>
      {isRecording && (
        <div className="flex h-10 items-end justify-center gap-1">
          {waveformData.map((v, idx) => (
            <div
              key={idx.toString()}
              className="w-1 rounded-full bg-jarvis-danger transition-all"
              style={{ height: `${8 + v * 24}px` }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
