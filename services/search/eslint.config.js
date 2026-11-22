import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/restrict-template-expressions": [
        "error",
        { allowNumber: true },
      ],
      "padding-line-between-statements": [
        "error",

        { blankLine: "always", prev: "const", next: "*" },
        { blankLine: "always", prev: "let", next: "*" },
        { blankLine: "always", prev: "*", next: "const" },
        { blankLine: "always", prev: "*", next: "let" },
        { blankLine: "always", prev: "*", next: "if" },
        { blankLine: "always", prev: "if", next: "*" },
        { blankLine: "any", prev: ["const", "let"], next: ["const", "let"] },
      ],
    },
  },
  {
    files: ["eslint.config.js"],
    ...tseslint.configs.disableTypeChecked,
  },
);
