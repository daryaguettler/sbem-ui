export interface GlobiColumnRole {
  key: string;
  label: string;
  yamlKey?: string | null;
  required?: boolean;
  recommended?: boolean;
  requiredGroup?: string;
  description?: string;
  /** GloBI's value rule in words, e.g. "Number from 0 to 1." */
  rule?: string | null;
  allowedValues?: string[];
}

export interface GisColumnMappings {
  [roleKey: string]: string | null | undefined;
}
