import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import "./index.css";
import Approvals from "./pages/Approvals";
import Briefings, { BriefingDetail } from "./pages/Briefings";
import Business, { TaskList } from "./pages/Business";
import Compliance from "./pages/Compliance";
import Costs from "./pages/Costs";
import Dashboard from "./pages/Dashboard";
import Finance from "./pages/Finance";
import Jurisdictions from "./pages/Jurisdictions";
import Login from "./pages/Login";
import Opportunity from "./pages/Opportunity";
import Pipeline from "./pages/Pipeline";
import Research, { RunDetail } from "./pages/Research";
import Search from "./pages/Search";
import Settings from "./pages/Settings";
import System from "./pages/System";

function App() {
  const { status } = useAuth();
  if (!status) return <Spinner />;
  if (!status.authenticated) return <Login />;
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/b/:slug" element={<Business />} />
        <Route path="/o/:id" element={<Opportunity />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/briefings" element={<Briefings />} />
        <Route path="/briefings/:id" element={<BriefingDetail />} />
        <Route path="/compliance" element={<Compliance />} />
        <Route path="/jurisdictions" element={<Jurisdictions />} />
        <Route path="/research" element={<Research />} />
        <Route path="/runs/:id" element={<RunDetail />} />
        <Route path="/finance" element={<Finance />} />
        <Route path="/costs" element={<Costs />} />
        <Route path="/tasks" element={<TaskList />} />
        <Route path="/system" element={<System />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/search" element={<Search />} />
        <Route path="*" element={<div className="text-slate-500">Not found.</div>} />
      </Routes>
    </Layout>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
