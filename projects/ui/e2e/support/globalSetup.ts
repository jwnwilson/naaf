export default async function globalSetup() {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch("http://localhost:8000/health");
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(
    "e2e stack API not healthy at http://localhost:8000/health within 60s — " +
    "start it with `make e2e` (which boots the scripted stack).",
  );
}
