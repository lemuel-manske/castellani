interface ProblemDetails {
  type: "about:blank";
  title: string;
  status: number;
  detail: string;
}

function problem(status: number, title: string, detail: string): ProblemDetails {
  return { type: "about:blank", title, status, detail };
}

export { problem };
export type { ProblemDetails };
