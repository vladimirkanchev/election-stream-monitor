export function success(data) {
  return { ok: true, data };
}

export function failureWithMetadata(code, message, details = null, metadata = {}) {
  return {
    ok: false,
    error: {
      code,
      message,
      details,
      backend_error_code: metadata.backend_error_code ?? null,
      status_reason: metadata.status_reason ?? null,
      status_detail: metadata.status_detail ?? null,
    },
  };
}

export function failure(code, message, details = null) {
  return failureWithMetadata(code, message, details);
}

export function isApiErrorPayload(value) {
  return Boolean(
    value
    && typeof value === "object"
    && typeof value.error_code === "string"
    && typeof value.detail === "string",
  );
}

export function mapApiErrorToBridgeFailure(code, fallbackMessage, error) {
  const apiPayload = error?.apiPayload;
  if (!isApiErrorPayload(apiPayload)) {
    return failure(
      code,
      fallbackMessage,
      error instanceof Error ? error.message : String(error),
    );
  }

  return failureWithMetadata(
    code,
    fallbackMessage,
    apiPayload.status_detail ?? apiPayload.detail,
    {
      backend_error_code: apiPayload.error_code,
      status_reason: apiPayload.status_reason ?? null,
      status_detail: apiPayload.status_detail ?? null,
    },
  );
}

export async function handleBridgeOperation(code, message, operation) {
  try {
    const data = await operation();
    return success(data);
  } catch (error) {
    return mapApiErrorToBridgeFailure(code, message, error);
  }
}
