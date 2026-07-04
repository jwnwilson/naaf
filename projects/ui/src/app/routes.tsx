import { Navigate } from "react-router-dom";
import type { RouteObject } from "react-router-dom";
import { AppShell } from "./AppShell";
import { BoardScreen } from "../modules/board/BoardScreen";
import { DashboardScreen } from "../modules/dashboard/DashboardScreen";
import { InboxScreen } from "../modules/inbox/InboxScreen";
import { DetailScreen } from "../modules/detail/DetailScreen";
import { SettingsScreen } from "../modules/settings/SettingsScreen";

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/projects?view=board" replace /> },
      { path: "dashboard", element: <DashboardScreen /> },
      { path: "inbox", element: <InboxScreen /> },
      { path: "inbox/:id", element: <InboxScreen /> },
      { path: "projects", element: <BoardScreen /> },
      { path: "projects/:projectId/items/:itemId", element: <DetailScreen /> },
      { path: "settings/agents", element: <SettingsScreen /> },
      { path: "settings/secrets", element: <SettingsScreen /> },
    ],
  },
];
