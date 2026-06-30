import { setupWorker } from "msw/browser";
import { handlers, mockOnlyHandlers } from "./handlers";

const live = import.meta.env.VITE_LIVE_API === "true";

export const worker = setupWorker(...(live ? mockOnlyHandlers : handlers));
