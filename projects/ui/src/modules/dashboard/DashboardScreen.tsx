import { ActivityFeed } from "./ActivityFeed";
import { MetricCards } from "./MetricCards";
import { RunningAgentsPanel } from "./RunningAgentsPanel";
import { TokenChart } from "./TokenChart";

export function DashboardScreen() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="sr-only">Dashboard</h1>
      <MetricCards />
      <div className="grid grid-cols-2 gap-4">
        <RunningAgentsPanel />
        <div className="flex flex-col gap-4">
          <TokenChart />
          <ActivityFeed />
        </div>
      </div>
    </div>
  );
}
