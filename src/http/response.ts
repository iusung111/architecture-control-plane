export class HttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly headers: HeadersInit = {},
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

export async function readJson<T>(request: Request): Promise<T> {
  try {
    return (await request.json()) as T;
  } catch {
    throw new HttpError(400, "invalid_json", "Request body must be valid JSON.");
  }
}

export function dataResponse(status: number, data: unknown, requestId: string | null): Response {
  return Response.json({ data, request_id: requestId }, { status });
}

export function errorResponse(error: HttpError, requestId: string | null): Response {
  return Response.json(
    {
      error: {
        code: error.code,
        details: error.details,
        message: error.message,
      },
      request_id: requestId,
    },
    { status: error.status, headers: error.headers },
  );
}
