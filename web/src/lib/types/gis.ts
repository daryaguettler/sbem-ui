export interface GlobiColumnRole {
  key: string;
  label: string;
  yamlKey?: string | null;
  required?: boolean;
  recommended?: boolean;
  requiredGroup?: string;
  description?: string;
}

export interface GisColumnMappings {
  [roleKey: string]: string | null | undefined;
}
