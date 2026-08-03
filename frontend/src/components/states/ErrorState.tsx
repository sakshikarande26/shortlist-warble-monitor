import { Surface } from "../ui/Surface";

interface ErrorStateProps {
  message: string;
  onRetry: () => void;
}

// No optimistic cover-ups: a fetch failure shows this, never stale/fake data.
export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <Surface className="px-6 py-10 text-center">
      <p className="text-[17px] font-medium text-ink">Something went wrong</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-ink-muted">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent/90"
      >
        Try again
      </button>
    </Surface>
  );
}
