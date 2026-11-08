import type { NextFunction, Request, Response } from "express";
import type { ZodTypeAny } from "zod";

/** Validates req.body with a Zod schema and answers 422 with structured errors. */
export function validateBody(schema: ZodTypeAny) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const result = schema.safeParse(req.body);
    if (!result.success) {
      res.status(422).json({
        error: "validation_error",
        message: "Request body failed validation",
        details: result.error.issues.map((i) => ({
          field: i.path.join("."),
          code: i.code,
          message: i.message,
        })),
      });
      return;
    }
    req.body = result.data;
    next();
  };
}
