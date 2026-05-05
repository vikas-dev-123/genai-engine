import { useCallback, useEffect, useRef, useState } from "react";

import { transcribe } from "../api/voice";

export function useVoice() {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [waveformData, setWaveformData] = useState<number[]>(Array(8).fill(0));

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stopVisualizer = () => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  };

  const tick = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) {
      return;
    }
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(data);
    const bands = 8;
    const perBand = Math.floor(data.length / bands);
    const values: number[] = [];
    for (let i = 0; i < bands; i += 1) {
      let sum = 0;
      for (let j = 0; j < perBand; j += 1) {
        sum += data[i * perBand + j];
      }
      const avg = sum / perBand / 255;
      values.push(Math.min(1, avg * 1.8));
    }
    setWaveformData(values);
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const startRecording = async () => {
    chunksRef.current = [];
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    const recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
    mediaRecorderRef.current = recorder;
    recorder.ondataavailable = (evt) => {
      if (evt.data.size > 0) {
        chunksRef.current.push(evt.data);
      }
    };
    recorder.start();

    const ctx = new AudioContext();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    const source = ctx.createMediaStreamSource(stream);
    source.connect(analyser);
    audioContextRef.current = ctx;
    analyserRef.current = analyser;
    sourceRef.current = source;
    stopVisualizer();
    rafRef.current = requestAnimationFrame(tick);
    setIsRecording(true);
  };

  const stopRecording = async () => {
    const recorder = mediaRecorderRef.current;
    if (!recorder) {
      return;
    }
    setIsRecording(false);
    stopVisualizer();
    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
      recorder.stop();
    });
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    sourceRef.current?.disconnect();
    sourceRef.current = null;
    await audioContextRef.current?.close();
    audioContextRef.current = null;
    analyserRef.current = null;

    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    chunksRef.current = [];
    setIsProcessing(true);
    try {
      const result = await transcribe(blob);
      setTranscript(result.transcript);
    } finally {
      setIsProcessing(false);
    }
  };

  const clearTranscript = () => setTranscript("");

  useEffect(
    () => () => {
      stopVisualizer();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    },
    [],
  );

  return {
    isRecording,
    isProcessing,
    transcript,
    waveformData,
    startRecording,
    stopRecording,
    clearTranscript,
  };
}
