import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderContent } from "./renderContent";

function highlighted(content: string, mentions: string[] = []) {
  const { container } = render(<p>{renderContent(content, mentions)}</p>);
  return Array.from(container.querySelectorAll("span")).map((s) => s.textContent);
}

describe("renderContent", () => {
  it("highlights @mentions that match a known role", () => {
    expect(highlighted("hey @agent-build-02 look", ["agent-build-02"])).toEqual(["@agent-build-02"]);
  });

  it("leaves a bare @token unstyled when it is not a listed mention", () => {
    expect(highlighted("email me @home please", [])).toEqual([]);
  });

  it("highlights inline `code` spans", () => {
    expect(highlighted("see `src/auth/refresh.py` now")).toEqual(["src/auth/refresh.py"]);
  });

  it("preserves the full text content across highlighted and plain runs", () => {
    const { container } = render(<p>{renderContent("@lead ping `x`", ["lead"])}</p>);
    expect(container.textContent).toBe("@lead ping x");
  });
});
