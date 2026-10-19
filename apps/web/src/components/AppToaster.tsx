/** Sonner `<Toaster />`, mounted once in the app shell. */

import { Toaster } from "sonner";

import { useTheme } from "@/lib/theme";

export function AppToaster(): JSX.Element {
  const { theme } = useTheme();
  return (
    <Toaster
      position="top-right"
      offset={16}
      closeButton
      theme={theme}
      toastOptions={{
        classNames: {
          toast:
            "rounded-xl border border-line bg-surface text-sm text-ink shadow-pop font-medium",
          description: "text-ink-muted text-xs font-normal",
          actionButton: "bg-brand-600 text-white",
          cancelButton: "bg-surface-sunken text-ink-secondary",
        },
        style: { fontFamily: "inherit" },
      }}
    />
  );
}
