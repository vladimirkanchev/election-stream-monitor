export class ApiHttpError extends Error {
  constructor(message, { status, apiPayload } = {}) {
    super(message);
    this.name = "ApiHttpError";
    this.status = status ?? null;
    this.apiPayload = apiPayload ?? null;
  }
}
