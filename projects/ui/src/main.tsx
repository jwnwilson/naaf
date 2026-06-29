import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

async function enableMocks() {
  if (import.meta.env.VITE_USE_MOCKS !== "true") return;
  const { worker } = await import("./lib/api/mocks/browser");
  await worker.start({ onUnhandledRequest: "bypass" });
}

enableMocks().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <div className="min-h-screen bg-bg-base text-text-1">NAAF UI — data layer ready</div>
    </StrictMode>,
  );
});
