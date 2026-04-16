export class HttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
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
        message: error.message,
      },
      request_id: requestId,
    },
    { status: error.status },
  );
}
