import { useEffect } from "react";

import { useAuth } from "./hooks/useAuth";
import { AuthForm } from "./components/AuthForm";
import { ChatWindow } from "./components/ChatWindow";
import { Sidebar } from "./components/Sidebar";

export default function App() {
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    document.documentElement.classList.add("dark");
    document.title = "Jarvis AI";
  }, []);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-jarvis-bg text-jarvis-muted">
        Initializing Jarvis…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthForm />;
  }

  return (
    <div className="flex h-screen bg-jarvis-bg text-jarvis-text">
      <Sidebar />
      <ChatWindow />
    </div>
  );
}
