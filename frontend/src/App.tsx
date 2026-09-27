import { useEffect } from "react";

import { useAuth } from "./hooks/useAuth";
import { AuthForm } from "./components/AuthForm";
import { ChatWindow } from "./components/ChatWindow";
import { Sidebar } from "./components/Sidebar";

export default function App() {
  const { isAuthenticated, isLoading } = useAuth();

  useEffect(() => {
    document.documentElement.classList.add("dark");
    document.title = "GenAI Engine";
  }, []);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-engine-bg text-engine-muted">
        Initializing GenAI Engine…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthForm />;
  }

  return (
    <div className="flex h-screen bg-engine-bg text-engine-text">
      <Sidebar />
      <ChatWindow />
    </div>
  );
}
