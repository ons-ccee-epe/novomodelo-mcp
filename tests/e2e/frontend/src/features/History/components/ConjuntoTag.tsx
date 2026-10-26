import { conjuntoColor, conjuntoLabel } from "@/shared/conjunto";

interface Props {
  conjunto: string;
  /** Torna o chip um botão (filtro). */
  onClick?: () => void;
  pressed?: boolean;
}

export function ConjuntoTag({ conjunto, onClick, pressed }: Props) {
  const style = { background: conjuntoColor(conjunto) };
  if (onClick) {
    return (
      <button
        type="button"
        className="cobre-tag"
        style={style}
        aria-pressed={pressed}
        onClick={onClick}
      >
        {conjuntoLabel(conjunto)}
      </button>
    );
  }
  return (
    <span className="cobre-tag" style={style}>
      {conjuntoLabel(conjunto)}
    </span>
  );
}
