import { Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/AppLayout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { AlertsPage } from "@/routes/AlertsPage";
import { AnalyticsPage } from "@/routes/AnalyticsPage";
import { DashboardPage } from "@/routes/DashboardPage";
import { FinancePage } from "@/routes/FinancePage";
import { FollowUpsPage } from "@/routes/FollowUpsPage";
import { LoginPage } from "@/routes/LoginPage";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { PatientDetailPage } from "@/routes/PatientDetailPage";
import { PatientsPage } from "@/routes/PatientsPage";

export default function App(): JSX.Element {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="/patients" element={<PatientsPage />} />
          <Route path="/patients/:patientId" element={<PatientDetailPage />} />
          <Route path="/finance" element={<FinancePage />} />
          <Route path="/follow-ups" element={<FollowUpsPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
