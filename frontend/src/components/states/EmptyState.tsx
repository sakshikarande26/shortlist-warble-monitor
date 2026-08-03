import { Link } from "react-router-dom";
import { DashedSurface } from "../ui/Surface";

interface EmptyStateProps {
  title: string;
  message: string;
  action?: { label: string; to: string };
}

export function EmptyState({ title, message, action }: EmptyStateProps) {
  return (
    <DashedSurface className="px-6 py-10 text-center">
      <p className="text-[17px] font-medium text-ink">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-ink-muted">{message}</p>
      {action && (
        <Link
          to={action.to}
          className="mt-4 inline-flex rounded-full bg-accent px-4 py-1.5 text-sm font-medium text-white transition-colors duration-150 hover:bg-accent/90"
        >
          {action.label}
        </Link>
      )}
    </DashedSurface>
  );
}
