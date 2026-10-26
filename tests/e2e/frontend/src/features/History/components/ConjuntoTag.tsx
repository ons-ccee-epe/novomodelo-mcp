import { conjuntoColor, conjuntoLabel } from "@/shared/conjunto";

interface Props {
  conjunto: string;
  /** Torna o chip um botão (filtro). */
  onClick?: () => void;
  pressed?: boolean;
}

export function ConjuntoTag({ conjunto, onClick, pressed }: Props) {
  const color = conjuntoColor(conjunto);
  if (onClick) {
    return (
      <button
        type="button"
        className="cobre-tag"
        style={{ "--tag-color": color } as React.CSSProperties}
        aria-pressed={pressed}
        onClick={onClick}
      >
        {conjuntoLabel(conjunto)}
      </button>
    );
  }
  return (
    <span className="cobre-tag" style={{ background: color }}>
      {conjuntoLabel(conjunto)}
    </span>
  );
}
