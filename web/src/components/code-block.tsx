"use client";

import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import oneDark from "react-syntax-highlighter/dist/esm/styles/prism/one-dark";

SyntaxHighlighter.registerLanguage("python", python);

// oneDark's own style object hardcodes "Fira Code"/"Fira Mono" on both the
// pre and code selectors — codeTagProps/customStyle alone don't win
// against that, so the theme's own font declarations are overridden
// directly to use the same mono face as the rest of the app.
const MONO_STACK = "var(--font-mono), ui-monospace, monospace";
const theme = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...oneDark['pre[class*="language-"]'],
    fontFamily: MONO_STACK,
  },
  'code[class*="language-"]': {
    ...oneDark['code[class*="language-"]'],
    fontFamily: MONO_STACK,
  },
};

export function CodeBlock({ code }: { code: string }) {
  return (
    <SyntaxHighlighter
      language="python"
      style={theme}
      customStyle={{
        margin: 0,
        borderRadius: "var(--radius-md)",
        fontSize: "0.8125rem",
      }}
    >
      {code}
    </SyntaxHighlighter>
  );
}
