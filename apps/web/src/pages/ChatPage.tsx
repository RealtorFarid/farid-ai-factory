/** Full-height chat with Atlas, including the approval gate. */

import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Chat } from "@/components/chat/Chat";
import { Card } from "@/components/ui";
import { useChat } from "@/hooks/useChat";

export function ChatPage() {
  const { entries, busy, send, choose, submit, reset } = useChat();
  const location = useLocation();
  const navigate = useNavigate();

  // A suggestion from the dashboard arrives as router state and is sent once.
  const seeded = useRef(false);
  const prompt = (location.state as { prompt?: string } | null)?.prompt;

  useEffect(() => {
    if (!prompt || seeded.current) return;
    seeded.current = true;
    void send(prompt);
    navigate(location.pathname, { replace: true, state: null });
  }, [prompt, send, navigate, location.pathname]);

  return (
    <div className="chat-page">
      <Card
        title="Atlas"
        hint="Reads your workspace · asks before acting"
        action={
          entries.length > 0 ? (
            <button className="card__action" onClick={reset}>
              New conversation
            </button>
          ) : undefined
        }
        flush
      >
        <Chat
          entries={entries}
          busy={busy}
          onSend={send}
          onChoose={choose}
          onSubmit={submit}
        />
      </Card>
    </div>
  );
}
