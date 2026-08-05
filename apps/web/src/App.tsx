import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { CapturePage } from "@/pages/Capture";
import { LeadDetailPage } from "@/pages/LeadDetail";
import { ChatPage } from "@/pages/ChatPage";
import { TodayPage } from "@/pages/Today";
import { ActivityPage, CalendarPage, InboxPage, LeadsPage } from "@/pages/Workspace";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<TodayPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/capture" element={<CapturePage />} />
        <Route path="/leads" element={<LeadsPage />} />
        <Route path="/leads/:leadId" element={<LeadDetailPage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="/activity" element={<ActivityPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
