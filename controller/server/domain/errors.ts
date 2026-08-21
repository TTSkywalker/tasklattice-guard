export class ControllerError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly detail: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ControllerError";
  }
}

export class NotFoundError extends ControllerError {
  constructor(resource: string, id: string) {
    super(`${resource} ${id} was not found.`, 404, "not_found", { resource, id });
  }
}

export class ConflictError extends ControllerError {
  constructor(message: string, code: string, detail: Record<string, unknown> = {}) {
    super(message, 409, code, detail);
  }
}

export class ValidationError extends ControllerError {
  constructor(message: string, detail: Record<string, unknown> = {}) {
    super(message, 422, "validation_failed", detail);
  }
}
